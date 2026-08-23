from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nodes.retrieval import (
    _amerge_bm25,
    _arerank,
    _expand_retrieval_query,
    _provenance_filter,
    _retrieval_filters,
    grade_node,
    retrieval_node,
    rewrite_node,
)
from src.config import Settings, get_settings
from src.retrieval.bm25 import BM25
from src.security import UserContext, UserRole


def _chunk(chunk_id: str, distance: float = 0.1, score=None, text: str = "nội dung") -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": "doc.md",
        "title": "Chính sách A",
        "category": "leave_policies",
        "is_official_policy": True,
        "page_start": None,
        "page_end": None,
        "distance": distance,
        "score": score,
    }


class TestRetrievalNode:
    def test_expands_hybrid_terms_for_mixed_language_documents(self):
        expanded = _expand_retrieval_query("Chính sách Hybrid như thế nào?")
        assert "WFH" in expanded
        assert "làm việc từ xa" in expanded
        assert "3-2" in expanded

    def test_leaves_other_queries_unchanged(self):
        query = "Tôi được nghỉ mấy ngày?"
        assert _expand_retrieval_query(query) == query

    def test_expands_internal_referral_query_for_qa_013(self):
        query = "Mình giới thiệu bạn ứng tuyển thì bạn mình nộp hồ sơ qua kênh nào?"
        expanded = _expand_retrieval_query(query)

        assert query in expanded
        assert "giới thiệu nội bộ" in expanded
        assert "referral" in expanded
        assert "kênh đăng tin" in expanded
        assert "nộp hồ sơ ứng viên" in expanded

    def test_does_not_expand_unrelated_self_introduction(self):
        query = "Giới thiệu giúp em chính sách nghỉ phép"
        assert _expand_retrieval_query(query) == query

    def test_expands_disciplinary_absence_query_for_qa_122(self):
        query = "Nếu em tự ý nghỉ làm nhưng chưa được phê duyệt thì sau bao nhiêu ngày bị sa thải?"
        expanded = _expand_retrieval_query(query)

        assert "tự ý bỏ việc" in expanded
        assert "05 ngày cộng dồn" in expanded
        assert "30 ngày" in expanded
        assert "lý do chính đáng" in expanded

    @pytest.mark.asyncio
    async def test_parses_chroma_query_result_into_chunks(self):
        chroma_result = {
            "ids": [["doc::0001", "doc::0002"]],
            "documents": [["Nội dung 1", "Nội dung 2"]],
            "metadatas": [
                [
                    {
                        "source_file": "doc.md",
                        "title": "Chính sách A",
                        "category": "leave_policies",
                        "is_official_policy": True,
                        "page_start": 1,
                        "page_end": 1,
                    },
                    {
                        "source_file": "doc2.md",
                        "title": "Chính sách B",
                        "category": "leave_policies",
                        "is_official_policy": False,
                    },
                ]
            ],
            "distances": [[0.12, 0.44]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1, 0.2, 0.3])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            # Không gọi reranker thật: unit test không được phụ thuộc mạng.
            patch("src.agents.nodes.retrieval._metadata_authorized", return_value=True),
            patch("src.agents.nodes.retrieval._metadata_lifecycle_allowed", return_value=True),
            patch("src.agents.nodes.retrieval._arerank", new=AsyncMock(side_effect=lambda q, c: c)),
        ):
            result = await retrieval_node(
                {
                    "query": "Tôi được nghỉ mấy ngày?",
                    "tenant_id": "nexatech",
                    "user_id": "u-test",
                    "department": "HR",
                    "user_role": "EMPLOYEE",
                }
            )

        chunks = result["retrieved_chunks"]
        assert len(chunks) == 2
        assert chunks[0]["chunk_id"] == "doc::0001"
        assert chunks[0]["distance"] == 0.12
        assert chunks[1]["is_official_policy"] is False
        # chunk thứ 2 không có page_start/page_end trong metadata -> None, không KeyError
        assert chunks[1]["page_start"] is None

    @pytest.mark.asyncio
    async def test_uses_rewritten_query_over_original_when_present(self):
        mock_collection = MagicMock()
        mock_collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        mock_embed = AsyncMock(return_value=[0.1])

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=mock_embed),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
        ):
            await retrieval_node(
                {
                    "query": "gốc",
                    "rewritten_query": "đã viết lại",
                    "tenant_id": "nexatech",
                    "user_id": "u-test",
                    "department": "HR",
                    "user_role": "EMPLOYEE",
                }
            )

        mock_embed.assert_awaited_once_with("đã viết lại")


class TestRetrievalNodeHybrid:
    """use_hybrid=False theo mặc định (xem TestRetrievalNode ở trên, không đổi
    hành vi). Các test này bật cờ tường minh và tắt lại sau khi xong — lru_cache
    (settings, _collection, _bm25_index) là module-level nên phải patch
    get_settings thay vì set field trực tiếp để không rò rỉ sang test khác."""

    def _hybrid_settings(self):
        settings = get_settings().model_copy(update={"use_hybrid": True, "use_reranker": False})
        return settings

    @pytest.mark.asyncio
    async def test_bm25_only_candidate_is_fetched_and_included(self):
        chroma_result = {
            "ids": [["a"]],
            "documents": [["nội dung a"]],
            "metadatas": [[{"source_file": "a.md", "title": "A", "category": "x", "is_official_policy": True}]],
            "distances": [[0.1]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result
        # "b" chỉ đến từ BM25, không nằm trong kết quả dense query ở trên -> phải
        # được lấy riêng qua collection.get(ids=["b"], ...).
        mock_collection.get.return_value = {
            "ids": ["b"],
            "documents": ["nội dung b"],
            "metadatas": [{"source_file": "b.md", "title": "B", "category": "x", "is_official_policy": False}],
        }
        bm25 = BM25(["a", "b"], ["nội dung a về nghỉ phép", "nội dung b về nghỉ phép đặc biệt"])

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            patch("src.agents.nodes.retrieval._bm25_index", return_value=bm25),
            patch("src.agents.nodes.retrieval.get_settings", return_value=self._hybrid_settings()),
            patch("src.agents.nodes.retrieval.get_authorization_engine") as auth,
        ):
            auth.return_value.get_authorized_source_files.return_value = ["a.md", "b.md"]
            result = await retrieval_node(
                {
                    "query": "nghỉ phép đặc biệt",
                    "tenant_id": "nexatech",
                    "user_id": "u-test",
                    "department": "HR",
                    "user_role": "EMPLOYEE",
                }
            )

        ids = {c["chunk_id"] for c in result["retrieved_chunks"]}
        assert "b" in ids
        b_chunk = next(c for c in result["retrieved_chunks"] if c["chunk_id"] == "b")
        assert b_chunk["text"] == "nội dung b"
        assert b_chunk["source_file"] == "b.md"

    @pytest.mark.asyncio
    async def test_bm25_does_not_reintroduce_restricted_runtime_upload(self):
        dense_chunk = _chunk("a", text="public policy")
        bm25 = BM25(["a", "secret"], ["public policy", "secret salary policy"])
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["secret"],
            "documents": ["secret salary policy"],
            "metadatas": [
                {
                    "source_file": "runtime-secret.md",
                    "authorization_source": "RUNTIME_UPLOAD",
                    "access_scope": "RESTRICTED",
                    "owner_user_id": "different-user",
                    "department": "HR",
                    "publication_status": "active",
                    "artifact_state": "frozen",
                    "retrieval_enabled": True,
                    "effective_date_ymd": 20250101,
                    "expiry_date_ymd": 99991231,
                }
            ],
        }
        user = UserContext(
            tenant_id="nexatech",
            user_id="employee-1",
            department="HR",
            role=UserRole.EMPLOYEE,
        )
        with (
            patch("src.agents.nodes.retrieval._bm25_index", return_value=bm25),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            patch("src.agents.nodes.retrieval.get_authorization_engine") as auth,
        ):
            auth.return_value.get_authorized_source_files.return_value = ["public.md"]
            result = await _amerge_bm25(
                "secret salary policy",
                ["a"],
                {"a": dense_chunk},
                self._hybrid_settings(),
                user_context=user,
                collection_name="tenant_nexatech_knowledge",
            )

        assert "secret" not in result

    @pytest.mark.asyncio
    async def test_bm25_load_failure_falls_back_to_dense_only(self):
        """_bm25_index() trả None khi tải corpus lỗi — hybrid phải tự tắt, không
        được làm chết cả request retrieval."""
        chroma_result = {
            "ids": [["a"]],
            "documents": [["nội dung a"]],
            "metadatas": [[{"source_file": "a.md", "title": "A", "category": "x", "is_official_policy": True}]],
            "distances": [[0.1]],
        }
        mock_collection = MagicMock()
        mock_collection.query.return_value = chroma_result

        with (
            patch("src.agents.nodes.retrieval._aembed_query", new=AsyncMock(return_value=[0.1])),
            patch("src.agents.nodes.retrieval._collection", return_value=mock_collection),
            patch("src.agents.nodes.retrieval._bm25_index", return_value=None),
            patch("src.agents.nodes.retrieval.get_settings", return_value=self._hybrid_settings()),
            patch("src.agents.nodes.retrieval._metadata_authorized", return_value=True),
            patch("src.agents.nodes.retrieval._metadata_lifecycle_allowed", return_value=True),
        ):
            result = await retrieval_node(
                {
                    "query": "câu hỏi",
                    "tenant_id": "nexatech",
                    "user_id": "u-test",
                    "department": "HR",
                    "user_role": "EMPLOYEE",
                }
            )

        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]


class TestRerank:
    @pytest.mark.asyncio
    async def test_reorders_by_relevance_score_and_attaches_it(self):
        chunks = [_chunk("a", distance=0.10), _chunk("b", distance=0.20), _chunk("c", distance=0.30)]
        # Gateway trả về thứ tự đã xếp lại: chunk "c" liên quan nhất.
        with patch("src.agents.nodes.retrieval.rerank", return_value=[(2, 0.91), (0, 0.40), (1, 0.02)]):
            result = await _arerank("câu hỏi", chunks)

        assert [c["chunk_id"] for c in result] == ["c", "a", "b"]
        assert result[0]["score"] == 0.91

    @pytest.mark.asyncio
    async def test_keeps_dense_order_when_gateway_fails(self):
        """Lỗi rerank chỉ được làm giảm chất lượng xếp hạng, không được làm chết
        cả câu hỏi (regression: bản cũ để lỗi tải model lọt ra ngoài node)."""
        chunks = [_chunk("a"), _chunk("b")]
        with patch("src.agents.nodes.retrieval.rerank", side_effect=RuntimeError("gateway 503")):
            result = await _arerank("câu hỏi", chunks)

        assert [c["chunk_id"] for c in result] == ["a", "b"]
        assert all(c["score"] is None for c in result)


class TestGradeNode:
    def test_filters_by_rerank_score_when_available(self):
        state = {"retrieved_chunks": [_chunk("a", score=0.8), _chunk("b", score=0.001)]}
        result = grade_node(state)
        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]

    def test_falls_back_to_distance_when_score_is_none(self):
        """Regression: bản cũ so `c.get("score", -99) > 0.0` trong khi
        RetrievedChunk luôn có key `score` = None → TypeError khi reranker vắng
        mặt, làm chết toàn bộ agent trên máy không cài được reranker."""
        state = {"retrieved_chunks": [_chunk("a", distance=0.1), _chunk("b", distance=0.9)]}
        result = grade_node(state)
        assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["a"]

    def test_returns_empty_instead_of_falling_back_to_top_k(self):
        """Không có chunk nào đủ liên quan thì phải để rỗng — generate sẽ báo
        thiếu thông tin và confidence thấp sẽ escalate. Fallback im lặng kiểu
        "lấy tạm top-3" làm tê liệt nhánh escalate."""
        state = {"retrieved_chunks": [_chunk("a", score=0.001), _chunk("b", score=0.0)]}
        assert grade_node(state)["retrieved_chunks"] == []

    def test_empty_chunks_stays_empty(self):
        result = grade_node({"retrieved_chunks": []})
        assert result["retrieved_chunks"] == []


class TestRewriteNode:
    @pytest.mark.asyncio
    async def test_increments_rewrite_count_and_sets_rewritten_query(self):
        llm = AsyncMock(return_value="  câu hỏi rõ hơn  ")
        with patch("src.agents.nodes.retrieval.acall_llm", new=llm):
            result = await rewrite_node({"query": "câu gốc", "rewrite_count": 1})
        assert result["rewritten_query"] == "câu hỏi rõ hơn"
        assert result["rewrite_count"] == 2
        assert llm.await_args.kwargs["model"] == get_settings().router_model


def _chunk_matches_condition(meta: dict, condition: dict) -> bool:
    """Đánh giá 1 điều kiện Chroma `where` cục bộ trên 1 dict metadata — dùng để
    test filter THẬT mà retrieval.py build ra, không phải một bản chép lại
    logic. field vắng mặt trong `meta` không khớp bất kỳ toán tử nào (đúng
    hành vi fail-closed của Chroma đã đo được với $eq/$ne trên field thiếu)."""
    ((field, spec),) = condition.items()
    if field not in meta:
        return False
    value = meta[field]
    if not isinstance(spec, dict):
        return value == spec
    ops = {
        "$eq": lambda v, target: v == target,
        "$ne": lambda v, target: v != target,
        "$lte": lambda v, target: v <= target,
        "$gte": lambda v, target: v >= target,
        "$nin": lambda v, target: v not in target,
        "$in": lambda v, target: v in target,
    }
    return all(ops[op](value, target) for op, target in spec.items())


def _chunk_matches_filter(meta: dict, where: dict) -> bool:
    if "$and" in where:
        return all(_chunk_matches_filter(meta, condition) for condition in where["$and"])
    if "$or" in where:
        return any(_chunk_matches_filter(meta, condition) for condition in where["$or"])
    return _chunk_matches_condition(meta, where)


class TestProvenanceFilter:
    """NexaTech Type-C contract v3.1.0 — filter bắt buộc cho 'frozen internal
    corpus'. $eq allowlist (không $ne blocklist): xem docstring _provenance_filter
    cho lý do — chunk index từ trước khi field tồn tại phải tự động bị loại."""

    def _settings(self, data_mode: str = "demo") -> Settings:
        return Settings(data_mode=data_mode)

    def test_demo_mode_requires_tenant_policy_and_frozen_lifecycle(self):
        where = _provenance_filter(
            self._settings("demo"),
            UserContext(tenant_id="nexatech", user_id="u-test", department="HR", role=UserRole.EMPLOYEE),
        )
        conditions = where["$and"]
        assert "source_file" in str(conditions[0])
        assert {"publication_status": "active"} in conditions
        assert {"artifact_state": "frozen"} in conditions
        assert {"retrieval_enabled": True} in conditions
        assert not any("provenance" in c for c in conditions)

    def test_production_mode_adds_provenance_condition(self):
        where = _provenance_filter(
            self._settings("production"),
            UserContext(tenant_id="nexatech", user_id="u-test", department="HR", role=UserRole.EMPLOYEE),
        )
        conditions = where["$and"]
        assert "source_file" in str(conditions[0])
        assert {"publication_status": "active"} in conditions
        assert {"artifact_state": "frozen"} in conditions
        assert {"retrieval_enabled": True} in conditions

    def test_temporal_conditions_present_and_numeric(self):
        """Chroma $lte/$gte CHỈ nhận int/float — đã đo lỗi thật (ValueError)
        khi thử chuỗi ISO trực tiếp. Field phải là *_ymd (int YYYYMMDD)."""
        where = _provenance_filter(
            self._settings("demo"),
            UserContext(tenant_id="nexatech", user_id="u-test", department="HR", role=UserRole.EMPLOYEE),
        )
        conditions = where["$and"]
        eff = next(c for c in conditions if "effective_date_ymd" in c)
        exp = next(c for c in conditions if "expiry_date_ymd" in c)
        assert isinstance(eff["effective_date_ymd"]["$lte"], int)
        assert isinstance(exp["expiry_date_ymd"]["$gte"], int)


class TestProvenanceFilterScenarios:
    """5 kịch bản fixture bắt buộc theo remediation NexaTech Type-C contract
    (2026-08-15) — đánh giá TRỰC TIẾP trên `where` dict thật do
    _provenance_filter() build ra (_chunk_matches_filter), không phải một bản
    diễn giải logic riêng."""

    QUERY_YMD = 20260815  # khớp currentDate phiên làm việc, không ảnh hưởng kết luận

    def _base_meta(self, **overrides) -> dict:
        meta = {
            "source_file": "01_chinh-sach-lam-them-gio-OT.md",
            "department": "HR",
            "access_category": "GENERAL",
            "authority": "tenant_official_policy",
            "publication_status": "active",
            "artifact_state": "frozen",
            "retrieval_enabled": True,
            "effective_date_ymd": 20250101,
            "expiry_date_ymd": 99991231,
            "provenance": "synthetic_demo",
        }
        meta.update(overrides)
        return meta

    def _where(self, data_mode: str = "demo") -> dict:
        return _provenance_filter(
            Settings(data_mode=data_mode),
            UserContext(tenant_id="nexatech", user_id="u-test", department="HR", role=UserRole.EMPLOYEE),
        )

    def test_future_effective_active_doc_not_retrieved(self):
        meta = self._base_meta(effective_date_ymd=20990101)  # có hiệu lực trong tương lai
        assert _chunk_matches_filter(meta, self._where()) is False

    def test_expired_doc_not_retrieved(self):
        meta = self._base_meta(expiry_date_ymd=20200101)  # đã hết hạn
        assert _chunk_matches_filter(meta, self._where()) is False

    def test_superseded_historical_doc_not_retrieved(self):
        meta = self._base_meta(publication_status="superseded")
        assert _chunk_matches_filter(meta, self._where()) is False

    def test_active_frozen_effective_doc_retrieved(self):
        meta = self._base_meta()
        assert _chunk_matches_filter(meta, self._where()) is True

    def test_unauthorized_source_file_not_retrieved(self):
        """Lifecycle-valid chunks are denied when source is outside the user's allowlist."""
        meta = self._base_meta(source_file="restricted-other-department.md")
        assert _chunk_matches_filter(meta, self._where()) is False

    def test_missing_field_chunk_not_retrieved(self):
        """Chunk index từ trước khi taxonomy/lifecycle tồn tại (không có field
        nào cả) phải tự động bị loại — đây chính là bug đã đo được và sửa
        bằng $eq allowlist thay vì $ne blocklist."""
        assert _chunk_matches_filter({}, self._where()) is False


def _runtime_allowed(meta: dict, user: UserContext) -> bool:
    return any(_chunk_matches_filter(meta, where) for where in _retrieval_filters(Settings(), user))


class TestRuntimeUploadAccessFilter:
    def _runtime_meta(self, **overrides) -> dict:
        meta = {
            "source_file": "runtime-private.md",
            "authorization_source": "RUNTIME_UPLOAD",
            "access_scope": "RESTRICTED",
            "owner_user_id": "owner-1",
            "department": "HR",
            "authorized_role": "MANAGER",
            "publication_status": "active",
            "artifact_state": "frozen",
            "retrieval_enabled": True,
            "effective_date_ymd": 20250101,
            "expiry_date_ymd": 99991231,
            "provenance": "customer_provided",
        }
        meta.update(overrides)
        return meta

    def test_restricted_upload_is_owner_only(self):
        owner = UserContext(tenant_id="nexatech", user_id="owner-1", department="HR", role=UserRole.EMPLOYEE)
        stranger = UserContext(tenant_id="nexatech", user_id="other-1", department="HR", role=UserRole.EMPLOYEE)
        assert _runtime_allowed(self._runtime_meta(), owner) is True
        assert _runtime_allowed(self._runtime_meta(), stranger) is False

    def test_department_and_role_scopes_are_exact(self):
        hr = UserContext(tenant_id="nexatech", user_id="u1", department="HR", role=UserRole.EMPLOYEE)
        eng = UserContext(tenant_id="nexatech", user_id="u2", department="ENGINEERING", role=UserRole.EMPLOYEE)
        hr_manager = UserContext(tenant_id="nexatech", user_id="u3", department="HR", role=UserRole.MANAGER)
        dept_doc = self._runtime_meta(access_scope="DEPARTMENT")
        role_doc = self._runtime_meta(access_scope="ROLE")
        assert _runtime_allowed(dept_doc, hr) is True
        assert _runtime_allowed(dept_doc, eng) is False
        assert _runtime_allowed(role_doc, hr_manager) is True
        assert _runtime_allowed(role_doc, hr) is False

    def test_company_wide_and_admin_are_still_department_bound(self):
        employee = UserContext(tenant_id="nexatech", user_id="u1", department="ENGINEERING", role=UserRole.EMPLOYEE)
        hr_employee = UserContext(tenant_id="nexatech", user_id="u2", department="HR", role=UserRole.EMPLOYEE)
        admin = UserContext(tenant_id="nexatech", user_id="admin-1", department="GENERAL", role=UserRole.ADMIN)
        assert _runtime_allowed(self._runtime_meta(access_scope="COMPANY_WIDE"), employee) is False
        assert _runtime_allowed(self._runtime_meta(access_scope="COMPANY_WIDE"), hr_employee) is True
        assert _runtime_allowed(self._runtime_meta(owner_user_id="someone-else"), admin) is False

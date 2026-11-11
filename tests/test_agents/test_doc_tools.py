import asyncio
import json

from src.agents import doc_tools
from src.agents.nodes import react

ACTIVE = {"publication_status": "active", "artifact_state": "frozen", "retrieval_enabled": True,
          "effective_date_ymd": 20200101, "expiry_date_ymd": 99991231}


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def get(self, where, include):
        rows = [r for r in self.rows if r[2]["source_file"] == where["source_file"]]
        return {"ids": [r[0] for r in rows], "documents": [r[1] for r in rows], "metadatas": [r[2] for r in rows]}


def _setup(monkeypatch, allowed):
    rows = [
        ("c2", "Hạn nộp chứng từ là 5 ngày làm việc.", {**ACTIVE, "source_file": "ke-toan.md", "chunk_index": 2, "heading_path": "3. Hạn nộp"}),
        ("c1", "Kế toán trưởng duyệt mọi khoản trên 10 triệu.", {**ACTIVE, "source_file": "ke-toan.md", "chunk_index": 1, "heading_path": "2. Duyệt"}),
        ("x1", "Bản cũ.", {**ACTIVE, "source_file": "cu.md", "publication_status": "archived"}),
    ]
    monkeypatch.setattr(doc_tools, "_collection", lambda name: FakeCollection(rows))

    class Engine:
        def get_authorized_source_files(self, ctx):
            return allowed

    monkeypatch.setattr(doc_tools, "get_authorization_engine", lambda: Engine())


STATE = {"tenant_id": "nexatech", "user_id": "u1", "department": "ACCOUNTING", "user_role": "EMPLOYEE"}


def test_get_document_orders_chunks_and_respects_registry(monkeypatch):
    _setup(monkeypatch, {"ke-toan.md", "cu.md"})
    chunks = asyncio.run(doc_tools.get_document(STATE, "ke-toan.md"))
    assert [c["chunk_id"] for c in chunks] == ["c1", "c2"]
    assert asyncio.run(doc_tools.get_document(STATE, "cu.md")) is None  # hết hiệu lực thì không đọc được

    _setup(monkeypatch, set())  # registry không cho xem
    assert asyncio.run(doc_tools.get_document(STATE, "ke-toan.md")) is None


def test_denied_and_missing_look_the_same_to_the_model(monkeypatch):
    _setup(monkeypatch, set())
    denied, _ = asyncio.run(react._tool_get_document(STATE, {"source_file": "ke-toan.md"}, "q"))
    missing, _ = asyncio.run(react._tool_get_document(STATE, {"source_file": "khong-co.md"}, "q"))
    assert denied == missing == doc_tools.NOT_AVAILABLE


def test_extraction_drops_values_without_verbatim_quote():
    src = "Hạn nộp chứng từ là 5 ngày làm việc.\nKế toán trưởng duyệt mọi khoản trên 10 triệu."
    raw = {
        "hạn nộp": {"value": "5 ngày làm việc", "quote": "Hạn nộp chứng từ là  5 ngày làm việc."},
        "người duyệt": {"value": "Giám đốc", "quote": "Giám đốc duyệt mọi khoản"},  # bịa
        "mức phạt": {"value": None, "quote": None},
    }
    out = doc_tools.verify_extraction(raw, ["hạn nộp", "người duyệt", "mức phạt", "không trả"], src)
    assert out["hạn nộp"]["grounded"] and out["hạn nộp"]["value"] == "5 ngày làm việc"
    assert out["người duyệt"] == {"value": None, "quote": None, "grounded": False}
    assert not out["mức phạt"]["grounded"] and not out["không trả"]["grounded"]


def test_extract_tool_returns_only_grounded_and_cites_evidence(monkeypatch):
    _setup(monkeypatch, {"ke-toan.md"})

    async def fake_llm(system, user, **kw):
        return json.dumps({
            "hạn nộp": {"value": "5 ngày làm việc", "quote": "Hạn nộp chứng từ là 5 ngày làm việc."},
            "người duyệt": {"value": "Giám đốc", "quote": "Giám đốc duyệt"},
        }, ensure_ascii=False)

    monkeypatch.setattr(doc_tools, "acall_llm", fake_llm)
    result, chunks = asyncio.run(react._tool_extract(STATE, {"source_file": "ke-toan.md", "fields": ["hạn nộp", "người duyệt"]}, "q"))
    assert json.loads(result.split(" Không có")[0]) == {"hạn nộp": "5 ngày làm việc"}
    assert "người duyệt" in result  # báo rõ trường không có căn cứ
    assert chunks[0]["category"] == "computed" and chunks[1]["chunk_id"] == "c2"


def test_compare_puts_relevant_sections_side_by_side(monkeypatch):
    _setup(monkeypatch, {"ke-toan.md"})
    result, evidence = asyncio.run(react._tool_compare(STATE, {"source_files": ["ke-toan.md", "khong-co.md"], "aspect": "hạn nộp chứng từ"}, "q"))
    assert "## " in result and doc_tools.NOT_AVAILABLE in result
    assert evidence[0]["chunk_id"] == "c2"  # mục khớp khía cạnh lên trước


def test_doc_tool_args_validated_by_registry():
    import pytest

    from src.agents.tools import ToolArgsError, parse_call

    ok = '{"source_files": ["a.md", "b.md"], "aspect": "hạn nộp"}'
    parse_call("compare_documents", ok)
    bad = [
        ("compare_documents", '{"source_files": ["a.md"], "aspect": "hạn nộp"}'),  # cần >= 2 file
        ("compare_documents", '{"source_files": ["../a.md", "b.md"], "aspect": "hạn nộp"}'),  # traversal trong list
        ("compare_documents", '{"source_files": ["x/a.md", "b.md"], "aspect": "hạn nộp"}'),
        ("get_document", '{"source_file": "..\\secret.md"}'),
        ("get_document", '{"source_file": "../../etc/passwd"}'),
        ("extract_structured", '{"source_file": "a.md", "fields": []}'),
    ]
    for name, raw in bad:
        with pytest.raises(ToolArgsError):
            parse_call(name, raw)

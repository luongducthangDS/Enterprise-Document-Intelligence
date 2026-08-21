"""Comprehensive end-to-end integration & regression test suite for Bug G6,
multi-turn context resolution, single-turn answering, and step-by-step streaming.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.escalation import confidence_node
from src.agents.nodes.generation import (
    ANSWER_TYPE_GENERAL_MARKER,
    ANSWER_TYPE_NA_MARKER,
    ANSWER_TYPE_PERSONALIZED_MARKER,
    INSUFFICIENT_MARKER,
    finalize_node,
    generate_node,
)
from src.agents.service import astream_answer


def _make_chunk(chunk_id: str, text: str, title: str = "Tài liệu HR", source_file: str = "doc.md", **kwargs) -> dict:
    base = {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": source_file,
        "title": title,
        "category": "general",
        "is_official_policy": True,
        "source_type": "official_policy",
        "authority": "tenant_official_policy",
        "provenance": "customer_provided",
        "tenant": "v-nova",
        "caveat": "",
        "heading_path": "Chính sách > Điều 1",
        "policy_status": "active",
        "page_start": 1,
        "page_end": 1,
        "distance": 0.1,
        "score": 0.85,
    }
    base.update(kwargs)
    return base


class TestComprehensiveG6AndMultiTurnFlows:
    """Kiểm tra toàn diện: Bug G6 + Trả lời 1 lần (Single-turn) + Từng bước (Multi-turn) + Streaming."""

    # -------------------------------------------------------------
    # 1. KIỂM TRA TOÀN DIỆN BUG G6 (5 CASES)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_g6_all_cases_prevent_false_escalation(self):
        """Xác nhận toàn bộ 5 case G6 không bị answerable=False hay kẹp điểm 0.1."""
        test_cases = [
            {
                "id": "qa_003",
                "query": "Tự ở lại làm OT không đăng ký trước có được tính không?",
                "chunk_text": "Làm thêm giờ phải đăng ký trước. Trường hợp đột xuất cần quản lý xác nhận bổ sung trong 24h. Không có xác nhận thì không được tính.",
                "llm_output": f"{ANSWER_TYPE_NA_MARKER} Theo quy định [Nguồn 1], OT không đăng ký trước không được tính lương trừ khi có quản lý xác nhận bổ sung trong vòng 24h.",
                "expected_answer_type": "not_applicable",
            },
            {
                "id": "qa_047",
                "query": "Người nước ngoài có phải đóng BHXH bắt buộc không?",
                "chunk_text": "NLĐ nước ngoài làm việc tại VN có HĐLĐ từ 1 năm phải đóng BHXH bắt buộc, trừ di chuyển nội bộ hoặc đã đủ tuổi nghỉ hưu.",
                "llm_output": f"{ANSWER_TYPE_GENERAL_MARKER} Người nước ngoài có HĐLĐ từ 1 năm phải đóng BHXH bắt buộc [Nguồn 1], trừ 2 ngoại lệ: di chuyển nội bộ hoặc đã đủ tuổi nghỉ hưu [Nguồn 1].",
                "expected_answer_type": "general_policy",
            },
            {
                "id": "qa_107",
                "query": "Được tài trợ 60 triệu học phí thì cam kết làm việc bao lâu?",
                "chunk_text": "Chi phí đào tạo trên 50 triệu yêu cầu cam kết làm việc tối thiểu 24 tháng.",
                "llm_output": f"{ANSWER_TYPE_GENERAL_MARKER} Đào tạo trên 50 triệu VNĐ yêu cầu cam kết làm việc tối thiểu 24 tháng [Nguồn 1].",
                "expected_answer_type": "general_policy",
            },
            {
                "id": "qa_109",
                "query": "Vừa qua thử việc có được tham gia BHSTN không?",
                "chunk_text": "BHSTN áp dụng cho nhân viên chính thức từ 3 tháng. Nhân viên vừa chuyển chính thức đủ điều kiện đăng ký ngay.",
                "llm_output": f"{ANSWER_TYPE_GENERAL_MARKER} Nhân viên vừa chuyển chính thức đủ điều kiện tham gia BHSTN trong kỳ đăng ký gần nhất [Nguồn 1].",
                "expected_answer_type": "general_policy",
            },
            {
                "id": "qa_123",
                "query": "Lịch làm việc chuẩn trong tuần là gì?",
                "chunk_text": "Thời gian làm việc chuẩn là thứ Hai đến thứ Sáu, 08:30 - 17:30.",
                "llm_output": f"{ANSWER_TYPE_NA_MARKER} Lịch làm việc chuẩn là từ thứ Hai đến thứ Sáu, 08:30 đến 17:30 [Nguồn 1].",
                "expected_answer_type": "not_applicable",
            },
        ]

        for tc in test_cases:
            chunk = _make_chunk(f"{tc['id']}::0001", tc["chunk_text"])
            with patch("src.agents.nodes.generation.acall_llm", new=AsyncMock(return_value=tc["llm_output"])):
                gen_state = await generate_node({"query": tc["query"], "retrieved_chunks": [chunk]})

            # Kiểm tra generate_node output
            assert gen_state["answerable"] is True, f"{tc['id']} phải answerable=True"
            assert gen_state["answer_type"] == tc["expected_answer_type"], f"{tc['id']} answer_type sai"
            assert INSUFFICIENT_MARKER not in gen_state["generated_answer"]
            assert len(gen_state["citations"]) >= 1

            # Kiểm tra confidence node không bị kẹp 0.1
            conf_state = confidence_node({
                "retrieved_chunks": [chunk],
                "hallucination_passed": True,
                "answerable": gen_state["answerable"],
            })
            assert conf_state["confidence_score"] >= 0.8, f"{tc['id']} confidence bị kẹp thấp: {conf_state['confidence_score']}"
            assert conf_state.get("escalate", False) is False, f"{tc['id']} bị escalate oan"

    # -------------------------------------------------------------
    # 2. KIỂM TRA TRẢ LỜI 1 LẦN (SINGLE-TURN DIRECT ANSWER)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_single_turn_answer_formatting_and_no_marker_leak(self):
        """Câu trả lời đơn lượt: không leak marker, trích xuất citation sạch sẽ."""
        chunk = _make_chunk("doc::001", "Chính sách nghỉ phép: 12 ngày phép năm tiêu chuẩn.")
        llm_raw = f"{ANSWER_TYPE_GENERAL_MARKER} Theo Chính sách nghỉ phép [Nguồn 1], tiêu chuẩn là 12 ngày phép năm."

        with patch("src.agents.nodes.generation.acall_llm", new=AsyncMock(return_value=llm_raw)):
            gen_res = await generate_node({"query": "Tôi có bao nhiêu ngày phép?", "retrieved_chunks": [chunk]})
            fin_res = finalize_node(gen_res)

        final_text = fin_res["response"]
        assert ANSWER_TYPE_GENERAL_MARKER not in final_text
        assert ANSWER_TYPE_PERSONALIZED_MARKER not in final_text
        assert ANSWER_TYPE_NA_MARKER not in final_text
        assert INSUFFICIENT_MARKER not in final_text
        assert "[Nguồn 1]" in final_text
        assert len(gen_res["citations"]) == 1

    # -------------------------------------------------------------
    # 3. KIỂM TRA TỪNG BƯỚC / ĐA LƯỢT (MULTI-TURN CONTEXT FLOW)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_multi_turn_step_by_step_conversation_flow(self):
        """Kiểm tra kịch bản hỏi đáp đa lượt:
        Lượt 1: Hỏi mơ hồ -> Bot làm rõ (needs_clarification=True).
        Lượt 2: Người dùng làm rõ -> Condense query giữ đúng ngữ cảnh -> Bot trả lời chính xác.
        Lượt 3: Người dùng hỏi follow-up ngắn gọn ("thế còn...") -> Condense nối cả 2 lượt trước.
        """
        from src.agents.nodes.condense import condense_node

        # Turn 1: User hỏi mơ hồ
        turn1_query = "Em muốn hỏi về nghỉ phép"
        turn1_history = []
        condense_t1 = await condense_node({"query": turn1_query, "history": turn1_history})
        assert condense_t1["condensed_query"] == turn1_query  # Không có history -> giữ nguyên

        # Turn 2: User trả lời làm rõ
        turn2_query = "Nghỉ phép năm khi làm đủ 12 tháng"
        turn2_history = [
            {"role": "user", "content": turn1_query},
            {"role": "assistant", "content": "Bạn muốn tìm hiểu về quy định nghỉ phép năm, phép ốm đau hay phép không lương ạ?"},
        ]
        mock_rewritten_t2 = "Quy định về số ngày nghỉ phép năm khi nhân viên làm việc đủ 12 tháng tại công ty."
        with patch("src.agents.nodes.condense.acall_llm", new=AsyncMock(return_value=mock_rewritten_t2)):
            condense_t2 = await condense_node({"query": turn2_query, "history": turn2_history})

        assert condense_t2["condensed_query"] == mock_rewritten_t2

        # Turn 3: User hỏi follow-up
        turn3_query = "Nếu không dùng hết thì được cộng dồn hay thanh toán tiền?"
        turn3_history = turn2_history + [
            {"role": "user", "content": turn2_query},
            {"role": "assistant", "content": "Theo quy định, nhân viên làm đủ 12 tháng được 12 ngày phép năm [Nguồn 1]."},
        ]
        mock_rewritten_t3 = "Quy định về việc cộng dồn hoặc thanh toán tiền cho ngày nghỉ phép năm chưa sử dụng hết."
        with patch("src.agents.nodes.condense.acall_llm", new=AsyncMock(return_value=mock_rewritten_t3)):
            condense_t3 = await condense_node({"query": turn3_query, "history": turn3_history})

        assert "phép năm" in condense_t3["condensed_query"].lower()

    # -------------------------------------------------------------
    # 4. KIỂM TRA STREAMING TỪNG BƯỚC (ASTREAM_ANSWER)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_streaming_step_by_step_events_and_reassembly(self):
        """Kiểm tra astream_answer phát đủ event và văn bản ghép lại nguyên vẹn."""
        async def _fake_steps(*args, **kwargs):
            yield {"condense": {"condensed_query": "Quy định làm thêm giờ"}}
            yield {"router": {"intent": "hr_question"}}
            yield {"retrieve": {"retrieved_chunks": [_make_chunk("c1", "OT tối đa 40h/tháng.")]}}
            yield {"grade": {"retrieved_chunks": [_make_chunk("c1", "OT tối đa 40h/tháng.")]}}
            yield {"generate": {
                "generated_answer": "Thời gian làm thêm giờ tối đa là 40h/tháng [Nguồn 1].",
                "citations": [_make_chunk("c1", "OT tối đa 40h/tháng.")],
                "answerable": True,
                "answer_type": "general_policy",
            }}
            yield {"hallucination_check": {"hallucination_passed": True}}
            yield {"confidence": {"confidence_score": 0.9, "escalate": False}}
            yield {"finalize": {
                "response": "Thời gian làm thêm giờ tối đa là 40h/tháng [Nguồn 1].",
                "citations": [_make_chunk("c1", "OT tối đa 40h/tháng.")],
            }}

        with patch("src.agents.service.agent.astream", side_effect=_fake_steps):
            history = [{"role": "user", "content": "Chào bot"}, {"role": "assistant", "content": "Chào bạn!"}]
            events = [e async for e in astream_answer("OT tối đa bao nhiêu giờ?", history=history)]

        event_types = [e["type"] for e in events]
        assert "status" in event_types
        assert "tool_start" in event_types
        assert "tool_end" in event_types
        assert "answer_delta" in event_types
        assert "citation" in event_types
        assert "done" in event_types

        # Ghép delta lại phải đúng 100%
        deltas = [e["content"] for e in events if e["type"] == "answer_delta"]
        reassembled = "".join(deltas)
        assert reassembled == "Thời gian làm thêm giờ tối đa là 40h/tháng [Nguồn 1]."

        # Done event phải chứa đầy đủ Pydantic contract DTO
        done_event = next(e for e in events if e["type"] == "done")
        assert done_event["intent"] == "hr_question"
        assert done_event["state"] == "ANSWER"
        assert done_event["answer"]["response"] == reassembled

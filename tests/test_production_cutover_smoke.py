import asyncio
import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.agents.state import AgentState
from src.agents.nodes.retrieval import retrieval_node
from src.security.models import UserContext, UserRole
from src.security.tenant_resolver import resolve_tenant_collection, validate_tenant_id


class TestProductionCutoverSmoke(unittest.IsolatedAsyncioTestCase):
    """Bộ kiểm thử Smoke Test cho Gate P0-D Production Retrieval Cutover."""

    def setUp(self):
        self.settings = get_settings()

    async def test_smoke_a_employee_company_wide(self):
        """Test A: Employee / NexaTech truy cập COMPANY_WIDE document -> ALLOW."""
        state = AgentState(
            query="Chính sách nghỉ phép năm quy định bao nhiêu ngày nghỉ tiêu chuẩn?",
            tenant_id="nexatech",
            user_role="EMPLOYEE",
            department="GENERAL",
            history=[],
            request_id="smoke-test-a",
            user_id="cutover-smoke-user",
        )
        res = await retrieval_node(state)
        chunks = res.get("retrieved_chunks", [])
        self.assertTrue(len(chunks) > 0, "Employee phải truy xuất được chunks chính sách")
        sources = [c["source_file"] for c in chunks]
        self.assertIn("07_chinh-sach-nghi-phep.md", sources)

    async def test_smoke_b_hr_department_sop(self):
        """Test B: HR / NexaTech truy cập HR SOP -> ALLOW."""
        state = AgentState(
            query="Quy trình tuyển dụng và phỏng vấn ứng viên của phòng nhân sự",
            tenant_id="nexatech",
            user_role="HR_OPERATOR",
            department="HR",
            history=[],
            request_id="smoke-test-b",
            user_id="cutover-smoke-user",
        )
        res = await retrieval_node(state)
        chunks = res.get("retrieved_chunks", [])
        sources = [c["source_file"] for c in chunks]
        self.assertIn("02_quy-trinh-tuyen-dung.md", sources)

    async def test_smoke_c_finance_denied_hr_sop(self):
        """Test C: Finance / NexaTech truy cập HR SOP -> DENY (0 chunk HR)."""
        state = AgentState(
            query="Quy trình tuyển dụng và phỏng vấn ứng viên của phòng nhân sự",
            tenant_id="nexatech",
            user_role="DEPARTMENT_USER",
            department="FINANCE",
            history=[],
            request_id="smoke-test-c",
            user_id="cutover-smoke-user",
        )
        res = await retrieval_node(state)
        chunks = res.get("retrieved_chunks", [])
        sources = [c["source_file"] for c in chunks]
        self.assertNotIn("02_quy-trinh-tuyen-dung.md", sources)
        self.assertNotIn("03_quy-trinh-onboarding.md", sources)

    def test_smoke_d_cross_tenant_isolation(self):
        """Test D: NexaTech user không thể truy cập Tenant B collection."""
        user_nexatech = UserContext(tenant_id="nexatech", user_id="nexa-user", department="GENERAL", role=UserRole.EMPLOYEE)
        user_tenant_b = UserContext(tenant_id="client_b", user_id="client-b-user", department="GENERAL", role=UserRole.EMPLOYEE)

        self.assertEqual(resolve_tenant_collection(user_nexatech), "tenant_nexatech_knowledge")
        self.assertEqual(resolve_tenant_collection(user_tenant_b), "tenant_client_b_knowledge")

    def test_smoke_e_client_cannot_override_tenant(self):
        """Test E: Client không thể tự truyền tenant_id không hợp lệ."""
        with self.assertRaises(ValueError):
            validate_tenant_id("tenant_b; DROP COLLECTION;")

    def test_smoke_f_missing_tenant_in_production_fails_closed(self):
        """Test F: Thiếu tenant_id trong môi trường PRODUCTION phải ném PermissionError (Fail-Closed)."""
        with patch.object(self.settings, "app_env", "production"):
            with self.assertRaises(PermissionError) as ctx:
                resolve_tenant_collection(user_context=UserContext.model_construct(tenant_id="", user_id="missing-tenant", department="GENERAL", role=UserRole.EMPLOYEE))
            self.assertIn("Missing authenticated tenant_id", str(ctx.exception))

    async def test_smoke_g_observability_audit_logging(self):
        """Test G: Quá trình retrieval ghi log audit chuẩn xác."""
        state = AgentState(
            query="Quy định hạn mức khách sạn công tác",
            tenant_id="nexatech",
            user_role="MANAGER",
            department="EXECUTIVE",
            history=[],
            request_id="smoke-test-g-audit",
            user_id="cutover-smoke-user",
        )
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            await retrieval_node(state)

        output = captured.getvalue()
        self.assertIn("[AUDIT-RETRIEVAL]", output)
        self.assertIn("req_id=smoke-test-g-audit", output)
        self.assertIn("tenant=nexatech", output)
        self.assertIn("collection=tenant_nexatech_knowledge", output)


if __name__ == "__main__":
    unittest.main()

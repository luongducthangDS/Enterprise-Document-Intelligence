import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, ".")


from src.ingestion.indexer import safe_delete_collection, delete_by_source_stem
from src.security.models import UserContext, UserRole
from src.security.tenant_resolver import (
    resolve_tenant_collection,
    get_tenant_collection_name,
    validate_tenant_id,
)


class TestSafetyGuardrailsP0A(unittest.TestCase):
    """Bộ kiểm thử đơn vị cho P0-A Safety Guardrails."""

    def test_destructive_reset_blocked_by_default(self):
        """Kiểm tra: Thao tác xóa collection bị chặn mặc định khi không có cờ xác nhận admin."""
        mock_client = MagicMock()
        with self.assertRaises(PermissionError) as ctx:
            safe_delete_collection(mock_client, "hr_documents", allow_destructive=False)
        self.assertIn("CRITICAL SAFETY GUARDRAIL", str(ctx.exception))
        mock_client.delete_collection.assert_not_called()

    def test_production_env_strictly_forbids_collection_drop(self):
        """Kiểm tra: Môi trường PRODUCTION tuyệt đối cấm xóa collection kể cả khi có cờ admin."""
        mock_client = MagicMock()
        with self.assertRaises(PermissionError) as ctx:
            safe_delete_collection(
                mock_client,
                "hr_documents",
                allow_destructive=True,
                environment_override="production",
            )
        self.assertIn("strictly PROHIBITED in PRODUCTION", str(ctx.exception))
        mock_client.delete_collection.assert_not_called()

    def test_tenant_resolver_valid_tenant(self):
        """Kiểm tra: Phân giải đúng namespace collection cho từng tenant."""
        self.assertEqual(get_tenant_collection_name("nexatech"), "tenant_nexatech_knowledge")
        self.assertEqual(get_tenant_collection_name("Vingroup"), "tenant_vingroup_knowledge")
        self.assertEqual(get_tenant_collection_name("client-abc_01"), "tenant_client-abc_01_knowledge")

    def test_tenant_resolver_rejects_invalid_tenant(self):
        """Kiểm tra: Chặn các chuỗi tenant_id không hợp lệ hoặc cố tình injection."""
        invalid_tenants = [
            "",
            "   ",
            "tenant/with/slashes",
            "tenant;DROP TABLE;",
            "tenant..name",
            "a" * 65,  # Quá 64 ký tự
        ]
        for invalid in invalid_tenants:
            with self.subTest(tenant=invalid):
                with self.assertRaises(ValueError):
                    validate_tenant_id(invalid)

    def test_client_cannot_override_trusted_tenant_context(self):
        """Kiểm tra: UserContext đọc từ state được chuẩn hóa an toàn."""
        user = UserContext.from_state({
            "user_role": "EMPLOYEE",
            "department": "IT",
            "tenant_id": "NexaTech",
        })
        self.assertEqual(user.tenant_id, "nexatech")
        resolved = resolve_tenant_collection(user)
        self.assertEqual(resolved, "tenant_nexatech_knowledge")

    def test_tenant_aware_deletion(self):
        """Kiểm tra: Lệnh xóa theo file được giới hạn trong phạm vi tenant khi có tenant_id."""
        mock_collection = MagicMock()
        delete_by_source_stem(mock_collection, "it_sop_01", tenant_id="nexatech")
        mock_collection.delete.assert_called_once_with(
            where={"$and": [{"source_stem": "it_sop_01"}, {"tenant": "nexatech"}]}
        )

        mock_collection_global = MagicMock()
        delete_by_source_stem(mock_collection_global, "bộ luật lao động", tenant_id=None)
        mock_collection_global.delete.assert_called_once_with(
            where={"source_stem": "bộ luật lao động"}
        )


if __name__ == "__main__":
    unittest.main()

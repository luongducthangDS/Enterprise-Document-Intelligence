import csv
import os
import sys
import unittest

sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client
from src.security.authorization import get_authorization_engine
from src.security.models import UserContext, UserRole
from src.security.tenant_resolver import resolve_tenant_collection, validate_tenant_id


EXPECTED_COUNTS = {
    "tenant_nexatech_knowledge": 269,
    "accounting_documents": 152,
    "product_documents": 82,
}
REGISTRIES = (
    "data/metadata/document_registry.csv",
    "data/metadata/accounting_document_registry.csv",
    "data/metadata/product_document_registry.csv",
)


class TestDomainCollectionParityAndSecurity(unittest.TestCase):
    """Read-only acceptance checks for the post-split three-domain index."""

    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.client = get_chroma_client(cls.settings)
        cls.collections = {name: cls.client.get_collection(name) for name in EXPECTED_COUNTS}

    def test_01_collection_baseline_counts(self):
        actual = {name: collection.count() for name, collection in self.collections.items()}
        self.assertEqual(actual, EXPECTED_COUNTS)

    def test_02_metadata_contract_per_collection(self):
        required_common = {
            "source_file",
            "department",
            "publication_status",
            "artifact_state",
            "retrieval_enabled",
            "effective_date_ymd",
            "expiry_date_ymd",
        }
        for name, collection in self.collections.items():
            sample = collection.get(limit=10, include=["metadatas"])
            self.assertTrue(sample["metadatas"], f"{name} phải có metadata")
            for metadata in sample["metadatas"]:
                self.assertTrue(
                    required_common <= set(metadata),
                    f"{name} thiếu metadata: {sorted(required_common - set(metadata))}",
                )
                self.assertEqual(metadata["publication_status"], "active")
                self.assertEqual(metadata["artifact_state"], "frozen")
                self.assertTrue(metadata["retrieval_enabled"])

        product_sample = self.collections["product_documents"].get(limit=10, include=["metadatas"])
        self.assertTrue(all(meta.get("owner") for meta in product_sample["metadatas"]))

    def test_03_collection_ids_are_disjoint(self):
        id_sets = {name: set(collection.get(include=[])["ids"]) for name, collection in self.collections.items()}
        names = list(id_sets)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                self.assertFalse(id_sets[left] & id_sets[right], f"{left} và {right} trùng chunk ID")

    def test_04_acl_registries_are_complete_and_safe(self):
        allowed_scopes = {"COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"}
        expected_documents = {
            REGISTRIES[0]: 31,
            REGISTRIES[1]: 10,
            REGISTRIES[2]: 32,
        }
        for path, expected_count in expected_documents.items():
            self.assertTrue(os.path.isfile(path), f"Thiếu ACL registry {path}")
            with open(path, encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), expected_count)
            self.assertFalse([row for row in rows if row.get("review_status") == "PENDING_REVIEW"])
            self.assertTrue(all(row.get("access_scope") in allowed_scopes for row in rows))

    def test_05_role_and_department_acl(self):
        auth_engine = get_authorization_engine()

        employee = UserContext(
            user_id="emp_user",
            department="HR",
            role=UserRole.EMPLOYEE,
            tenant_id="nexatech",
        )
        employee_files = auth_engine.get_authorized_source_files(employee)
        self.assertIn("07_chinh-sach-nghi-phep.md", employee_files)
        self.assertNotIn("02_quy-trinh-tuyen-dung.md", employee_files)

        it_user = UserContext(
            user_id="it_user",
            department="IT",
            role=UserRole.DEPARTMENT_USER,
            tenant_id="nexatech",
        )
        it_files = auth_engine.get_authorized_source_files(it_user)
        self.assertIn("it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md", it_files)
        self.assertNotIn("02_quy-trinh-tuyen-dung.md", it_files)

    def test_06_tenant_routing_and_injection_denial(self):
        nexatech = UserContext(
            user_id="emp_1",
            department="IT",
            role=UserRole.EMPLOYEE,
            tenant_id="nexatech",
        )
        external = UserContext(
            user_id="emp_2",
            department="IT",
            role=UserRole.EMPLOYEE,
            tenant_id="tenant_b",
        )
        self.assertEqual(resolve_tenant_collection(nexatech), "tenant_nexatech_knowledge")
        self.assertEqual(resolve_tenant_collection(external), "tenant_tenant_b_knowledge")
        with self.assertRaises(ValueError):
            validate_tenant_id("tenant_b; DROP COLLECTION;")


if __name__ == "__main__":
    unittest.main()

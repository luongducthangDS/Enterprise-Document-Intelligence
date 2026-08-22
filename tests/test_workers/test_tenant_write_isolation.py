from unittest.mock import MagicMock

import pytest

from src.config import get_settings
from src.ingestion.chunk_builder import tenant_scoped_chunk_id
from src.ingestion.indexer import (
    collection_name_for_department,
    delete_by_source_stem,
)


def test_chunk_ids_differ_for_same_file_across_tenants():
    assert tenant_scoped_chunk_id("tenant-a", "policy", 0) == "tenant-a:policy::0000"
    assert tenant_scoped_chunk_id("tenant-b", "policy", 0) == "tenant-b:policy::0000"


@pytest.mark.parametrize("department", ["HR", "Product", "Accounting"])
def test_collection_names_differ_for_non_active_tenants(department):
    settings = get_settings()
    active = collection_name_for_department(department, settings, "nexatech")
    external = collection_name_for_department(department, settings, "tenant-b")
    assert active != external
    assert external.startswith("tenant_tenant-b_")


def test_delete_requires_and_filters_explicit_tenant():
    collection = MagicMock()
    delete_by_source_stem(collection, "policy", "tenant-a")
    collection.delete.assert_called_once_with(
        where={"$and": [{"source_stem": "policy"}, {"tenant": "tenant-a"}]}
    )

    with pytest.raises(ValueError):
        delete_by_source_stem(collection, "policy", "")

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

EXPECTED_BACKEND_TABLES = {
    "users",
    "profiles",
    "conversations",
    "messages",
    "tickets",
    "documents",
    "chat_requests",
    "ingestion_jobs",
    "index_jobs",
    "evaluation_runs",
}


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def test_migration_numbers_are_unique_and_contiguous():
    files = _migration_files()
    numbers = [int(path.name.split("_", 1)[0]) for path in files]

    assert len(numbers) == len(set(numbers)), "Mỗi migration phải có số thứ tự riêng"
    assert numbers == list(range(1, max(numbers) + 1))


def test_initial_schema_rebuilds_all_backend_tables():
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    tables = set(re.findall(r"(?im)^create table public\.([a-z_]+)", sql))

    assert tables == EXPECTED_BACKEND_TABLES
    assert "references public.users(id)" in sql
    assert "references auth.users(id)" not in sql


def test_runtime_tables_keep_durable_state_columns():
    sql = (MIGRATIONS_DIR / "0001_initial_schema.sql").read_text(encoding="utf-8")
    required_fragments = {
        "chat_requests": ("state text", "retry_count integer", "retryable boolean"),
        "ingestion_jobs": ("state text", "stage text", "progress_percent integer"),
        "index_jobs": ("state text", "stage text", "active_index_version text"),
        "evaluation_runs": ("state text", "metrics jsonb", "quality_gate text"),
    }

    for table, fragments in required_fragments.items():
        table_sql = re.search(
            rf"(?is)create table public\.{table}\s*\((.*?)\n\);",
            sql,
        )
        assert table_sql is not None, table
        for fragment in fragments:
            assert fragment in table_sql.group(1), f"{table}: thiếu {fragment}"


def test_authority_migration_runs_after_runtime_registry():
    names = [path.name for path in _migration_files()]

    assert "0005_hr_runtime_registry.sql" in names
    assert "0006_document_authority_provenance.sql" in names
    assert not any(name.startswith("0004_document_authority") for name in names)

"""Read-only verification for the release database schema and RLS posture."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import engine  # noqa: E402

REQUIRED_TABLES = {
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


async def main() -> int:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    select c.relname, c.relrowsecurity
                    from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'public' and c.relkind = 'r'
                    order by c.relname
                    """
                )
            )
        ).all()
        triggers = (
            await connection.execute(
                text(
                    """
                    select tgname
                    from pg_trigger
                    where not tgisinternal
                      and tgrelid = 'public.profiles'::regclass
                    order by tgname
                    """
                )
            )
        ).scalars().all()

    await engine.dispose()
    table_rls = dict(rows)
    missing = sorted(REQUIRED_TABLES - table_rls.keys())
    rls_disabled = sorted(name for name in REQUIRED_TABLES if name in table_rls and not table_rls[name])
    guard_present = "trg_prevent_self_privilege_escalation" in triggers

    print(f"required_tables={len(REQUIRED_TABLES) - len(missing)}/{len(REQUIRED_TABLES)}")
    print(f"missing_tables={','.join(missing) or 'none'}")
    print(f"rls_disabled={','.join(rls_disabled) or 'none'}")
    print(f"profile_privilege_guard={'present' if guard_present else 'missing'}")
    return 0 if not missing and not rls_disabled and guard_present else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

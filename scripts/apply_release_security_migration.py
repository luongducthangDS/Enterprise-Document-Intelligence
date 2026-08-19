"""Apply only the idempotent release-security reconciliation migration."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import engine  # noqa: E402

MIGRATION = ROOT / "supabase" / "migrations" / "0007_release_security_reconciliation.sql"


async def apply() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    raw = await engine.raw_connection()
    try:
        driver = raw.driver_connection
        transaction = driver.transaction()
        await transaction.start()
        try:
            await driver.execute(sql)
        except Exception:
            await transaction.rollback()
            raise
        else:
            await transaction.commit()
    finally:
        raw.close()
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually mutate the configured release database")
    args = parser.parse_args()
    if not args.apply:
        print(f"dry_run migration={MIGRATION.name}; pass --apply to execute")
        return 0
    asyncio.run(apply())
    print(f"applied migration={MIGRATION.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

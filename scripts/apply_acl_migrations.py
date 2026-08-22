import asyncio
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))
from app.core.database import engine
MIGRATIONS=(ROOT / "supabase/migrations/0006_document_authority_provenance.sql", ROOT / "supabase/migrations/0008_document_runtime_acl.sql", ROOT / "supabase/migrations/0009_access_admin_audit.sql")
async def main():
    raw=await engine.raw_connection()
    try:
        driver=raw.driver_connection
        tx=driver.transaction()
        await tx.start()
        try:
            for migration in MIGRATIONS:
                print(f"applying {migration.name}")
                await driver.execute(migration.read_text(encoding="utf-8"))
        except Exception:
            await tx.rollback()
            raise
        else:
            await tx.commit()
    finally:
        raw.close()
        await engine.dispose()
    print("committed")
if __name__ == "__main__":
    asyncio.run(main())

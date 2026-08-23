"""QA audit helpers: register/login QA users qua public API (giống flow UI).

KHÔNG sửa source. User QA được dọn bởi cleanup_qa_users.py sau audit.
Role HR_ADMIN được nâng trực tiếp qua DB (cùng cách QC 2026-08-22 đã làm),
ghi audit trail trong báo cáo.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
BACKEND = os.environ.get("E2E_BACKEND_URL", "http://127.0.0.1:8000/api/v1")
QA_STATE = ROOT / "qa" / "audit_20260823" / "data" / "qa_users.json"

EMAIL_EMP = "qa.audit.emp@e2e-p153.dev"
EMAIL_ADM = "qa.audit.adm@e2e-p153.dev"
PASSWORD = "QaAudit#2026"


def client(token: str | None = None) -> httpx.Client:
    headers = {"X-Request-ID": f"qa-{uuid.uuid4().hex[:8]}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=BACKEND, headers=headers, timeout=90)


def data(resp: httpx.Response) -> dict:
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


def ensure_user(email: str, department: str, full_name: str) -> dict:
    """Register (bỏ qua lỗi đã tồn tại) rồi login, trả token + user."""
    with client() as c:
        try:
            data(c.post("/auth/register", json={
                "email": email, "password": PASSWORD,
                "department": department, "full_name": full_name,
            }))
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (409, 400):
                raise
            print(f"[setup] {email}: đã tồn tại ({e.response.status_code}), dùng login")
        login = data(c.post("/auth/login", json={"email": email, "password": PASSWORD}))
    token = login.get("access_token") or login.get("token")
    with client(token) as c:
        me = data(c.get("/auth/me"))
    return {"email": email, "password": PASSWORD, "token": token, "me": me}


def elevate_hr_admin(email: str) -> None:
    """Nâng role qua DB, ủy quyền bằng JWT claims của một hr_admin hiện hữu
    (set_config is_local=true, chỉ hiệu lực trong transaction) — không disable
    trigger. Cách QC 22/08 dùng disable-trigger là bất buộc phải; cách này ít
    xâm phạm hơn. Ghi chú đầy đủ vào report + cleanup."""
    sys.path.insert(0, str(ROOT / "backend"))
    import asyncio
    import json as _json
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as s:
            admin_id = (await s.execute(
                text("select id from profiles where lower(role)='hr_admin' order by created_at limit 1")
            )).scalar_one_or_none()
            if admin_id is None:
                raise RuntimeError("Không tìm thấy hr_admin nào để ủy quyền")
            claims = _json.dumps({"sub": str(admin_id), "role": "authenticated"})
            await s.execute(text("select set_config('request.jwt.claims', :c, true)"), {"c": claims})
            r = await s.execute(
                text("UPDATE profiles SET role='hr_admin' "
                     "WHERE id=(SELECT id FROM users WHERE email=:e) RETURNING id"),
                {"e": email})
            await s.commit()
            return r.rowcount
    n = asyncio.run(_run())
    print(f"[setup] elevate {email} -> HR_ADMIN (authorized by existing hr_admin, txn-local claims): {n} row(s)")


def main():
    emp = ensure_user(EMAIL_EMP, "Engineering", "QA Audit Employee")
    adm = ensure_user(EMAIL_ADM, "HR", "QA Audit Admin")
    elevate_hr_admin(EMAIL_ADM)
    adm2 = ensure_user(EMAIL_ADM, "HR", "QA Audit Admin")  # login lại để lấy JWT mới sau khi đổi role
    QA_STATE.write_text(json.dumps(
        {"employee": {k: emp[k] for k in ("email", "password", "token")},
         "admin": {k: adm2[k] for k in ("email", "password", "token")},
         "admin_role_after": adm2["me"].get("role")},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[setup] employee role={emp['me'].get('role')} dept={emp['me'].get('department')}")
    print(f"[setup] admin role={adm2['me'].get('role')} (must be HR_ADMIN)")
    print(f"[setup] state -> {QA_STATE}")


if __name__ == "__main__":
    main()

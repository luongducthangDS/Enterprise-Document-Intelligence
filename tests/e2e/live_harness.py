"""Live E2E harness cho P-153 — chạyagainst services thật (backend:8000, agent:8001).

Chỉ dùng cho tests/e2e/test_live_e2e.py khi E2E_LIVE=1. Không mock gì trừ khi
ghi chú rõ trong report. Mọi kết quả được ghi vào artifacts JSON để tổng hợp report.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx

BACKEND = os.environ.get("E2E_BACKEND_URL", "http://127.0.0.1:8000/api/v1")
AGENT = os.environ.get("E2E_AGENT_URL", "http://127.0.0.1:8001/api/v1/agent")
ARTIFACTS = Path(os.environ.get("E2E_ARTIFACTS", "logs/e2e_results.json"))

TERMINAL = {"COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"}
RESULTS: list[dict] = []


def record(entry: dict) -> None:
    RESULTS.append(entry)
    ARTIFACTS.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if ARTIFACTS.exists():
        try:
            existing = [e for e in json.loads(ARTIFACTS.read_text(encoding="utf-8")) if e.get("id") != entry["id"]]
        except Exception:
            existing = []
    ARTIFACTS.write_text(json.dumps(existing + RESULTS[-1:], ensure_ascii=False, indent=1), encoding="utf-8")


class BackendClient:
    def __init__(self, token: str | None = None, timeout: float = 60.0):
        headers = {"X-Request-ID": f"e2e-{uuid.uuid4().hex[:8]}"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url=BACKEND, headers=headers, timeout=timeout)

    @staticmethod
    def _data(resp: httpx.Response) -> dict:
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body) if isinstance(body, dict) else body

    # ---- auth ----
    def register(self, email: str, password: str, department: str, full_name: str) -> dict:
        return self._data(
            self.client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "department": department,
                    "full_name": full_name,
                },
            )
        )

    def login(self, email: str, password: str) -> dict:
        return self._data(self.client.post("/auth/login", json={"email": email, "password": password}))

    def me(self) -> dict:
        return self._data(self.client.get("/auth/me"))

    # ---- conversations / chat ----
    def create_conversation(self) -> dict:
        return self._data(self.client.post("/conversations", json={}))

    def ask(self, conversation_id: str, question: str) -> dict:
        return self._data(
            self.client.post(
                "/chat/requests",
                json={"conversation_id": conversation_id, "question": question},
            )
        )

    def poll(self, chat_request_id: str, deadline_s: float = 240.0, interval: float = 1.5) -> dict:
        start = time.time()
        while time.time() - start < deadline_s:
            data = self._data(self.client.get(f"/chat/requests/{chat_request_id}"))
            if data.get("state") in TERMINAL:
                data["_poll_s"] = round(time.time() - start, 1)
                return data
            time.sleep(interval)
        raise TimeoutError(f"chat request {chat_request_id} chưa terminal sau {deadline_s}s")

    def ask_and_wait(self, conversation_id: str, question: str, deadline_s: float = 240.0) -> dict:
        created = self.ask(conversation_id, question)
        return self.poll(created["chat_request_id"], deadline_s=deadline_s)

    # ---- documents (admin) ----
    def upload_document(self, path: str, **fields) -> dict:
        with open(path, "rb") as f:
            files = {"file": (Path(path).name, f)}
            return self._data(self.client.post("/documents", files=files, data=fields))

    def list_documents(self) -> dict:
        return self._data(self.client.get("/documents"))

    def archive_document(self, document_id: str) -> dict:
        return self._data(self.client.post(f"/documents/{document_id}/archive"))

    def ingestion_job(self, job_id: str) -> dict:
        return self._data(self.client.get(f"/ingestion-jobs/{job_id}"))

    def wait_ingestion(self, job_id: str, deadline_s: float = 300.0) -> dict:
        start = time.time()
        while time.time() - start < deadline_s:
            data = self.ingestion_job(job_id)
            if str(data.get("state", "")).upper() in {"SUCCEEDED", "FAILED", "COMPLETED", "CANCELLED"}:
                return data
            time.sleep(3)
        raise TimeoutError(f"ingestion job {job_id} chưa xong sau {deadline_s}s")


def agent_status(token: str) -> httpx.Response:
    return httpx.get(f"{AGENT}/status", headers={"X-Service-Token": token}, timeout=30)


_IDENTITY_FIELDS = ("request_id", "user_id", "tenant_id", "department", "user_role")


def identity_signature(payload: dict, secret: str) -> str:
    """HMAC-SHA256 giống backend/app/services/ai_agent_client.py::_identity_signature."""
    import hashlib
    import hmac as _hmac

    identity = {f: payload.get(f) for f in _IDENTITY_FIELDS}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def agent_query(token: str, query: str, tenant: str, dept: str = "HR", role: str = "EMPLOYEE",
                history: list | None = None, user: str = "e2e-user") -> httpx.Response:
    payload = {
        "query": query,
        "request_id": f"e2e-{uuid.uuid4().hex[:10]}",
        "user_id": user,
        "tenant_id": tenant,
        "department": dept,
        "user_role": role,
    }
    if history:
        payload["history"] = history
    headers = {"X-Service-Token": token, "X-Identity-Signature": identity_signature(payload, token)}
    return httpx.post(f"{AGENT}/query", json=payload, headers=headers, timeout=300)


def check(name: str, category: str, expected: str, passed: bool, actual: str, severity: str = "HIGH", notes: str = "") -> bool:
    record(
        {
            "id": name,
            "category": category,
            "expected": expected,
            "actual": actual[:800],
            "status": "PASS" if passed else "FAIL",
            "severity": severity,
            "notes": notes,
            "ts": time.strftime("%H:%M:%S"),
        }
    )
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {actual[:160]}")
    return passed

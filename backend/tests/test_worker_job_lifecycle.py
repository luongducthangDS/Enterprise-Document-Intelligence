import io
import uuid

import httpx
import pytest
from app.domain.models.documents import IngestionJobDB
from app.domain.models.evaluation import EvaluationRunDB
from app.domain.models.index_job import IndexJobDB
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.evaluation import EvaluationRunRequest
from app.schemas.indexes import IndexRebuildRequest
from app.services.document_service import DocumentService, _resolve_document_department
from app.services.evaluation_service import EvaluationService
from app.services.index_service import IndexService
from app.services.worker_job_client import WorkerJobClient
from fastapi import UploadFile
from sqlalchemy import update


class FakeWorkerClient:
    def __init__(self) -> None:
        self.kinds: dict[str, str] = {}

    async def submit_ingestion(self, payload: dict) -> dict:
        self.kinds[payload["job_id"]] = "INGESTION"
        assert payload["content_base64"]
        assert payload["tenant"] == "nexatech"
        assert payload["access_scope"] == "RESTRICTED"
        assert payload["owner_user_id"]
        assert payload["authorization_source"] == "RUNTIME_UPLOAD"
        return {"job_id": payload["job_id"], "state": "QUEUED"}

    async def submit_index_rebuild(self, payload: dict) -> dict:
        self.kinds[payload["job_id"]] = "INDEX_REBUILD"
        assert payload["tenant"] == "nexatech"
        return {"job_id": payload["job_id"], "state": "QUEUED"}

    async def submit_evaluation(self, payload: dict) -> dict:
        self.kinds[payload["job_id"]] = "EVALUATION"
        return {"job_id": payload["job_id"], "state": "QUEUED"}

    async def get_status(self, job_id: str) -> dict:
        kind = self.kinds[job_id]
        results = {
            "INGESTION": {
                "chunk_count": 3,
                "processed_path": "data/processed/worker_lifecycle.md",
                "chunks_path": "data/chunks/worker_lifecycle.json",
            },
            "INDEX_REBUILD": {"active_index_version": "v1.1"},
            "EVALUATION": {
                "metrics": {"recall_at_k": 0.9, "answer_correctness": 0.85},
                "quality_gate": "PASSED",
            },
        }
        return {
            "job_id": job_id,
            "kind": kind,
            "state": "COMPLETED",
            "stage": "COMPLETED",
            "progress_percent": 100,
            "result": results[kind],
            "error": None,
        }


@pytest.mark.asyncio
async def test_backend_worker_jobs_reach_terminal_state_and_persist_results(db_session):
    user_id = uuid.uuid4()
    user = UserDB(id=user_id, email=f"worker-{user_id}@company.com", hashed_password="hash")
    user.profile = ProfileDB(id=user_id, display_name="Worker Admin", role="HR_ADMIN", department="HR")
    db_session.add(user)
    await db_session.execute(update(IndexJobDB).values(state="COMPLETED"))
    await db_session.execute(update(EvaluationRunDB).values(state="COMPLETED"))
    await db_session.commit()

    fake = FakeWorkerClient()
    services = (DocumentService, IndexService, EvaluationService)
    previous = [(service.worker_client, service.worker_dispatch_enabled) for service in services]
    for service in services:
        service.worker_client = fake
        service.worker_dispatch_enabled = True

    actor = {"user_id": str(user_id), "role": "HR_ADMIN"}
    try:
        upload = UploadFile(filename="worker_lifecycle.pdf", file=io.BytesIO(b"%PDF-1.4 worker lifecycle"))
        document = await DocumentService.upload_document(db_session, actor, upload)
        ingestion = await DocumentService.get_ingestion_job(db_session, actor, document["ingestion_job_id"])
        assert ingestion["state"] == "COMPLETED"
        assert (await db_session.get(IngestionJobDB, uuid.UUID(document["ingestion_job_id"]))).chunk_count == 3

        index = await IndexService.create_rebuild_job(
            db_session,
            actor,
            IndexRebuildRequest(document_ids=[document["document_id"]], strategy="REPLACE"),
        )
        index_status = await IndexService.get_rebuild_job_status(db_session, actor, index["job_id"])
        assert index_status["state"] == "COMPLETED"
        assert index_status["active_index_version"] == "v1.1"

        evaluation = await EvaluationService.create_evaluation_run(
            db_session,
            actor,
            EvaluationRunRequest(dataset_id="evalset_hr_v2"),
        )
        evaluation_status = await EvaluationService.get_evaluation_run_status(db_session, actor, evaluation["run_id"])
        assert evaluation_status["state"] == "COMPLETED"
        assert evaluation_status["metrics"]["recall_at_5"] == 0.9
        assert evaluation_status["quality_gate"] == "PASSED"
    finally:
        for service, (client, enabled) in zip(services, previous, strict=True):
            service.worker_client = client
            service.worker_dispatch_enabled = enabled


@pytest.mark.asyncio
async def test_worker_client_uses_agent_worker_contract_paths():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"job_id": "job-1", "state": "QUEUED"})

    client = WorkerJobClient(
        base_url="http://agent/api/v1/agent",
        service_token="secret",
        transport=httpx.MockTransport(handler),
    )
    await client.submit_ingestion({"job_id": "job-1"})
    await client.get_status("job-1")

    assert [request.url.path for request in requests] == [
        "/api/v1/agent/jobs/ingestion",
        "/api/v1/agent/jobs/job-1",
    ]
    assert all(request.headers["X-Service-Token"] == "secret" for request in requests)


def test_document_department_routing():
    assert _resolve_document_department("Product", "GENERAL") == "Product"
    assert _resolve_document_department(None, "PRD") == "Product"
    assert _resolve_document_department(None, "invoices_and_tax") == "ACCOUNTING"
    assert _resolve_document_department(None, "LEAVE") == "HR"
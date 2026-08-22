"""HMAC verification for Backend-to-Agent identity propagation."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import HTTPException, status

from src.config import Settings


IDENTITY_FIELDS = ("request_id", "user_id", "tenant_id", "department", "user_role")


def canonical_identity(payload: dict) -> bytes:
    identity = {field: payload.get(field) for field in IDENTITY_FIELDS}
    return json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_identity(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_identity(payload), hashlib.sha256).hexdigest()


def verify_identity_signature(
    payload: dict,
    signature: str | None,
    settings: Settings,
) -> None:
    secret = settings.agent_service_token
    if not secret:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent identity verification is not configured",
            )
        return
    expected = sign_identity(payload, secret)
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signed user identity",
        )

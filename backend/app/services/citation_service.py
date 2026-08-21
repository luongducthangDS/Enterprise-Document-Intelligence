import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.documents import DocumentDB
from app.domain.models.messages import MessageDB
from app.services.content_safety import redact_pii


class CitationService:
    @staticmethod
    def _find_in_rows(rows: list[Any], citation_id: str) -> dict[str, Any] | None:
        for row in rows:
            if not isinstance(row.citations, list):
                continue
            for item in row.citations:
                if isinstance(item, dict) and item.get("citation_id") == citation_id:
                    return item
        return None

    @classmethod
    async def get_citation_detail(
        cls,
        db: AsyncSession,
        citation_id: str,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        clean_cit_id = citation_id.strip()
        user_id = uuid.UUID(str(user.get("user_id")))

        msg_res = await db.execute(
            select(MessageDB)
            .join(ConversationDB, ConversationDB.id == MessageDB.conversation_id)
            .where(MessageDB.citations.is_not(None), ConversationDB.user_id == user_id)
        )
        found_item = cls._find_in_rows(list(msg_res.scalars().all()), clean_cit_id)

        if not found_item:
            req_res = await db.execute(
                select(ChatRequestDB).where(
                    ChatRequestDB.citations.is_not(None),
                    ChatRequestDB.user_id == user_id,
                )
            )
            found_item = cls._find_in_rows(list(req_res.scalars().all()), clean_cit_id)

        if not found_item:
            raise NotFoundError(
                code="CITATION_NOT_FOUND",
                message="Không tìm thấy thông tin trích dẫn tài liệu.",
            )

        title = found_item.get("title") or found_item.get("source_file") or "Tài liệu chính sách"
        source_file = found_item.get("source_file")
        doc_res = await db.execute(
            select(DocumentDB).where(or_(DocumentDB.title == title, DocumentDB.source_file == source_file))
        )
        doc = doc_res.scalars().first()

        document_id = f"doc_{clean_cit_id}"
        version = found_item.get("version")
        effective_date = found_item.get("effective_date")
        document_status = "ACTIVE"
        caveat = None
        if doc:
            document_id = str(doc.id)
            version = doc.version or version
            effective_date = doc.effective_date or effective_date
            document_status = doc.status
            caveat = redact_pii(doc.caveat) or None
            user_role = user.get("role", "EMPLOYEE")
            if doc.confidentiality in ("RESTRICTED", "CONFIDENTIAL") and user_role not in (
                "HR_ADMIN",
                "SUPER_ADMIN",
            ):
                raise ForbiddenError(
                    code="DOCUMENT_ACCESS_DENIED",
                    message="Bạn không có quyền truy cập trích dẫn từ tài liệu này.",
                )

        is_official_policy = found_item.get("is_official_policy")
        if is_official_policy is None:
            is_official_policy = doc.is_official_policy if doc else True
        else:
            is_official_policy = bool(is_official_policy)

        source_type = found_item.get("source_type") or (doc.source_type if doc else None)

        return {
            "citation_id": clean_cit_id,
            "document": {
                "document_id": document_id,
                "title": redact_pii(title),
                "version": version,
                "effective_date": effective_date,
                "status": document_status,
                "is_official_policy": is_official_policy,
                "source_type": source_type,
            },
            "location": {
                "page": found_item.get("page") or found_item.get("page_start"),
                "sheet": found_item.get("sheet") or found_item.get("sheet_start"),
                "section": redact_pii(found_item.get("section")) or None,
                "chunk_id": found_item.get("chunk_id"),
            },
            "excerpt": redact_pii(found_item.get("excerpt")),
            "caveat": caveat,
            "conflict_warning": bool(found_item.get("conflict_warning", False)),
            "is_official_policy": is_official_policy,
            "source_type": source_type,
        }

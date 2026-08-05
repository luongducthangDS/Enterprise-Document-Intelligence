from datetime import UTC, datetime

from app.domain.models.user import Base
from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column


class TicketDB(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    user_query: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="OPEN")  # OPEN, IN_PROGRESS, RESOLVED
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

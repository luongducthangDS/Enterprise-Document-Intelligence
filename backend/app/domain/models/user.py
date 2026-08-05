import uuid
from datetime import UTC, datetime

from app.core.database import Base
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    role: Mapped[str] = mapped_column(String, default="EMPLOYEE", nullable=False)  # EMPLOYEE, HR_ADMIN
    department: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

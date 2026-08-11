import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domain.models.user import UserDB


class ProfileDB(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    display_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="",
    )

    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="employee",
    )

    employment_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="full_time",
    )

    department: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    business_unit: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    contract_type: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    tenure_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    seniority_years: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    access_level: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="self_only",
    )

    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    manager: Mapped["ProfileDB | None"] = relationship(
        "ProfileDB",
        remote_side=[id],
        back_populates="subordinates",
    )

    subordinates: Mapped[list["ProfileDB"]] = relationship(
        "ProfileDB",
        back_populates="manager",
    )

    user: Mapped["UserDB"] = relationship(
        "UserDB",
        back_populates="profile",
    )

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UserSettings(Base):
    """App-specific settings for a Keycloak user."""

    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    preferred_llm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_targets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

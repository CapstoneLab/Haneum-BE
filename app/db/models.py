import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

json_type = JSON().with_variant(JSONB(), "postgresql")


class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"
    __table_args__ = (
        CheckConstraint("local_score BETWEEN 0 AND 100", name="ck_analysis_local_score"),
        CheckConstraint("rule_score BETWEEN 0 AND 100", name="ck_analysis_rule_score"),
        CheckConstraint(
            "llm_score IS NULL OR llm_score BETWEEN 0 AND 100",
            name="ck_analysis_llm_score",
        ),
        CheckConstraint(
            "llm_confidence IS NULL OR llm_confidence BETWEEN 0 AND 1",
            name="ck_analysis_llm_confidence",
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed','fallback')",
            name="ck_analysis_status",
        ),
        Index("ix_analysis_device_created", "device_id", "created_at"),
        Index("ix_analysis_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_name: Mapped[str | None] = mapped_column(String(150))
    masked_text: Mapped[str | None] = mapped_column(Text)
    local_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    rule_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    llm_score: Mapped[int | None] = mapped_column(SmallInteger)
    llm_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(50))
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    risk_log: Mapped["RiskLog | None"] = relationship(
        back_populates="analysis_request", uselist=False
    )


class RiskLog(Base):
    __tablename__ = "risk_logs"
    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_score"),
        CheckConstraint("risk_level IN ('safe','warning','danger')", name="ck_risk_level"),
        CheckConstraint(
            "user_action IN ('none','continue','cancel','edit')", name="ck_user_action"
        ),
        Index("ix_risk_device_created", "device_id", "created_at"),
        Index("ix_risk_level", "risk_level"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    analysis_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("analysis_requests.id", ondelete="SET NULL"), unique=True
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_name: Mapped[str | None] = mapped_column(String(150))
    risk_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="safe")
    risk_types: Mapped[list[str]] = mapped_column(json_type, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(Text)
    masked_text: Mapped[str | None] = mapped_column(Text)
    user_action: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    analysis_request: Mapped[AnalysisRequest | None] = relationship(back_populates="risk_log")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    risk_sensitivity: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    tts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vibration_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    large_text_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    high_contrast_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("risk_sensitivity IN ('low','normal','high')", name="ck_risk_sensitivity"),
    )

"""Create MVP analysis, risk log, and settings tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("app_name", sa.String(length=150), nullable=True),
        sa.Column("masked_text", sa.Text(), nullable=True),
        sa.Column("local_score", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("rule_score", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("llm_score", sa.SmallInteger(), nullable=True),
        sa.Column("llm_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("llm_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("local_score BETWEEN 0 AND 100", name="ck_analysis_local_score"),
        sa.CheckConstraint("rule_score BETWEEN 0 AND 100", name="ck_analysis_rule_score"),
        sa.CheckConstraint(
            "llm_score IS NULL OR llm_score BETWEEN 0 AND 100", name="ck_analysis_llm_score"
        ),
        sa.CheckConstraint(
            "llm_confidence IS NULL OR llm_confidence BETWEEN 0 AND 1",
            name="ck_analysis_llm_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed','fallback')",
            name="ck_analysis_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_device_created", "analysis_requests", ["device_id", "created_at"])
    op.create_index("ix_analysis_status", "analysis_requests", ["status"])

    op.create_table(
        "risk_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_request_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("app_name", sa.String(length=150), nullable=True),
        sa.Column("risk_score", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("risk_level", sa.String(length=20), server_default="safe", nullable=False),
        sa.Column(
            "risk_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("masked_text", sa.Text(), nullable=True),
        sa.Column("user_action", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("llm_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_score"),
        sa.CheckConstraint("risk_level IN ('safe','warning','danger')", name="ck_risk_level"),
        sa.CheckConstraint(
            "user_action IN ('none','continue','cancel','edit')", name="ck_user_action"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_request_id"], ["analysis_requests.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_request_id"),
    )
    op.create_index("ix_risk_device_created", "risk_logs", ["device_id", "created_at"])
    op.create_index("ix_risk_level", "risk_logs", ["risk_level"])

    op.create_table(
        "user_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column(
            "risk_sensitivity", sa.String(length=20), server_default="normal", nullable=False
        ),
        sa.Column("tts_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("vibration_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("large_text_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("high_contrast_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "risk_sensitivity IN ('low','normal','high')", name="ck_risk_sensitivity"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_user_settings_device_id", "user_settings", ["device_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_settings_device_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_index("ix_risk_level", table_name="risk_logs")
    op.drop_index("ix_risk_device_created", table_name="risk_logs")
    op.drop_table("risk_logs")
    op.drop_index("ix_analysis_status", table_name="analysis_requests")
    op.drop_index("ix_analysis_device_created", table_name="analysis_requests")
    op.drop_table("analysis_requests")

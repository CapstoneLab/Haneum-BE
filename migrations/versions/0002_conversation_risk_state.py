"""Add persistent per-conversation risk state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_conversation_risk_state"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_requests", sa.Column("conversation_id", sa.String(length=150), nullable=True)
    )
    op.add_column(
        "analysis_requests", sa.Column("message_id", sa.String(length=100), nullable=True)
    )
    op.add_column("risk_logs", sa.Column("conversation_id", sa.String(length=150), nullable=True))

    op.create_table(
        "conversation_risk_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.String(length=150), nullable=False),
        sa.Column("app_name", sa.String(length=150), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("suspicion_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("peak_score", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "risk_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_suspicious_message_id", sa.String(length=100), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('normal','watching','confirmed')",
            name="ck_conversation_risk_status",
        ),
        sa.CheckConstraint(
            "suspicion_count >= 0", name="ck_conversation_suspicion_count"
        ),
        sa.CheckConstraint(
            "peak_score BETWEEN 0 AND 100", name="ck_conversation_peak_score"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id", "conversation_id", name="uq_conversation_risk_device_conversation"
        ),
    )
    op.create_index(
        "ix_conversation_risk_device_updated",
        "conversation_risk_profiles",
        ["device_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_risk_device_updated", table_name="conversation_risk_profiles"
    )
    op.drop_table("conversation_risk_profiles")
    op.drop_column("risk_logs", "conversation_id")
    op.drop_column("analysis_requests", "message_id")
    op.drop_column("analysis_requests", "conversation_id")

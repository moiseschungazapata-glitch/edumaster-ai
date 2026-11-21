"""Institution-scoped transactional audit of academic changes."""
import sqlalchemy as sa
from alembic import op

revision = "0005_audit"
down_revision = "0004_guidance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_institution_time", "audit_records", ["institution_id", "occurred_at"])
    op.execute("ALTER TABLE public.audit_records ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_index("ix_audit_institution_time", table_name="audit_records")
    op.drop_table("audit_records")

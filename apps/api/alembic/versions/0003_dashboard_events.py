"""Timestamp academic actions and record institution-scoped dashboard events."""
import sqlalchemy as sa
from alembic import op

revision = "0003_dashboard_events"
down_revision = "0002_academic"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("enrollments", "lesson_progress", "attempts"):
        op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("academic_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_academic_events_institution_id", "academic_events", ["institution_id", "id"])
    op.execute("ALTER TABLE public.academic_events ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_index("ix_academic_events_institution_id", table_name="academic_events")
    op.drop_table("academic_events")
    for table in ("attempts", "lesson_progress", "enrollments"):
        op.drop_column(table, "created_at")

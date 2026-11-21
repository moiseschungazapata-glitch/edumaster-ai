"""Rule-based guidance and human-reviewed recommendation lifecycle."""
import sqlalchemy as sa
from alembic import op

revision = "0004_guidance"
down_revision = "0003_dashboard_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("expected_impact", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=False, server_default=""),
        sa.Column("feedback_useful", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("student_id", "course_id", "kind"),
        sa.CheckConstraint("status IN ('new','accepted','discarded','completed','expired')", name="valid_recommendation_status"),
        sa.CheckConstraint("review_status IN ('pending','approved','rejected')", name="valid_recommendation_review"),
    )
    op.create_index("ix_recommendations_student", "recommendations", ["student_id", "status"])
    op.create_index("ix_recommendations_institution", "recommendations", ["institution_id", "review_status"])
    op.execute("ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_index("ix_recommendations_institution", table_name="recommendations")
    op.drop_index("ix_recommendations_student", table_name="recommendations")
    op.drop_table("recommendations")

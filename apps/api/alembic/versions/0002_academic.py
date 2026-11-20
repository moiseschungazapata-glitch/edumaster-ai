"""Academic courses, learning paths, enrollments and assessment progress."""
import sqlalchemy as sa
from alembic import op

revision = "0002_academic"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("courses", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False), sa.Column("teacher_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("learning_paths", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False))
    op.create_table("path_courses", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("path_id", sa.Uuid(), sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False), sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("path_id", "course_id"), sa.UniqueConstraint("path_id", "position"))
    op.create_table("lessons", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.UniqueConstraint("course_id", "position"))
    op.create_table("activities", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("title", sa.String(160), nullable=False), sa.Column("question", sa.Text(), nullable=False), sa.Column("options_json", sa.Text(), nullable=False), sa.Column("correct_index", sa.Integer(), nullable=False), sa.Column("passing_score", sa.Integer(), nullable=False, server_default="100"), sa.UniqueConstraint("course_id", "position"))
    op.create_table("enrollments", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False), sa.Column("student_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False), sa.UniqueConstraint("course_id", "student_id"))
    op.create_table("lesson_progress", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("lesson_id", sa.Uuid(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False), sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False), sa.UniqueConstraint("lesson_id", "enrollment_id"))
    op.create_table("attempts", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("activity_id", sa.Uuid(), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False), sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False), sa.Column("selected_index", sa.Integer(), nullable=False), sa.Column("score", sa.Integer(), nullable=False))
    for table in ("courses", "learning_paths", "path_courses", "lessons", "activities", "enrollments", "lesson_progress", "attempts"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.create_index("ix_courses_institution", "courses", ["institution_id"])
    op.create_index("ix_paths_institution", "learning_paths", ["institution_id"])
    op.create_index("ix_attempts_enrollment", "attempts", ["enrollment_id"])


def downgrade():
    op.drop_index("ix_attempts_enrollment", table_name="attempts")
    op.drop_index("ix_paths_institution", table_name="learning_paths")
    op.drop_index("ix_courses_institution", table_name="courses")
    for table in ("attempts", "lesson_progress", "enrollments", "activities", "lessons", "path_courses", "learning_paths", "courses"):
        op.drop_table(table)

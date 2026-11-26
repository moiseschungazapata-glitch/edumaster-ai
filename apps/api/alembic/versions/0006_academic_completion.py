"""Assign learning paths and issue verifiable course certificates."""
import sqlalchemy as sa
from alembic import op

revision = "0006_academic_completion"
down_revision = "0005_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_paths", sa.Column("objective", sa.Text(), nullable=False, server_default=""))
    op.add_column("learning_paths", sa.Column("prerequisites_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("learning_paths", sa.Column("duration_hours", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("learning_paths", sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("course_units",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("course_id", "position"))
    op.add_column("lessons", sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("course_units.id"), nullable=True))
    op.add_column("courses", sa.Column("code", sa.String(40), nullable=True))
    op.add_column("courses", sa.Column("level", sa.String(24), nullable=False, server_default="beginner"))
    op.add_column("courses", sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("courses", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("courses", sa.Column("certificate_heading", sa.String(120), nullable=False, server_default="Certificado de finalización"))
    op.add_column("courses", sa.Column("certificate_signatory", sa.String(120), nullable=False, server_default="EduMaster.ai"))
    op.create_unique_constraint("uq_courses_institution_code", "courses", ["institution_id", "code"])
    op.add_column("activities", sa.Column("kind", sa.String(24), nullable=False, server_default="multiple_choice"))
    op.add_column("activities", sa.Column("correct_answer", sa.String(500), nullable=False, server_default=""))
    op.add_column("activities", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("activities", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("activities", sa.Column("rubric", sa.Text(), nullable=False, server_default=""))
    op.add_column("activities", sa.Column("weight", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("attempts", sa.Column("text_answer", sa.String(500), nullable=False, server_default=""))
    op.add_column("attempts", sa.Column("feedback", sa.String(1000), nullable=False, server_default=""))
    op.add_column("attempts", sa.Column("artifact", sa.LargeBinary(), nullable=True))
    op.add_column("attempts", sa.Column("artifact_mime", sa.String(50), nullable=False, server_default=""))
    op.add_column("attempts", sa.Column("graded_by", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True))
    op.add_column("attempts", sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("cohorts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.UniqueConstraint("institution_id", "name"))
    op.create_table("cohort_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cohort_id", sa.Uuid(), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.UniqueConstraint("cohort_id", "student_id"))
    op.create_table("lesson_resources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lesson_id", sa.Uuid(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("artifact", sa.LargeBinary(), nullable=True),
        sa.Column("artifact_mime", sa.String(50), nullable=False, server_default=""))
    op.create_table("lesson_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lesson_id", sa.Uuid(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("lesson_id", "version"))
    op.create_table("path_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("path_id", sa.Uuid(), sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("path_id", "student_id"))
    op.create_table("path_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("path_id", sa.Uuid(), sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("path_id", "version"))
    op.create_table("certificates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id"), nullable=False),
        sa.Column("verification_code", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("enrollment_id"))
    for table in ("cohorts", "cohort_members", "lesson_resources", "lesson_versions", "course_units", "path_assignments", "path_versions", "certificates"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute("INSERT INTO public.lesson_versions (id, lesson_id, version, title, content, changed_by, changed_at) SELECT gen_random_uuid(), l.id, 1, l.title, l.content, c.teacher_id, now() FROM public.lessons l JOIN public.courses c ON c.id = l.course_id")
    op.execute("INSERT INTO public.path_versions (id, path_id, version, snapshot_json, changed_by, changed_at) SELECT gen_random_uuid(), p.id, 1, json_build_object('title', p.title, 'description', p.description, 'objective', p.objective, 'prerequisite_ids', '[]'::json, 'duration_hours', p.duration_hours, 'course_ids', coalesce((SELECT json_agg(pc.course_id ORDER BY pc.position) FROM public.path_courses pc WHERE pc.path_id = p.id), '[]'::json))::text, coalesce((SELECT c.teacher_id FROM public.path_courses pc JOIN public.courses c ON c.id = pc.course_id WHERE pc.path_id = p.id ORDER BY pc.position LIMIT 1), (SELECT pr.id FROM public.profiles pr WHERE pr.institution_id = p.institution_id LIMIT 1)), now() FROM public.learning_paths p WHERE EXISTS (SELECT 1 FROM public.profiles pr WHERE pr.institution_id = p.institution_id)")
    op.create_index("ix_path_assignments_student", "path_assignments", ["student_id"])


def downgrade():
    op.drop_index("ix_path_assignments_student", table_name="path_assignments")
    op.drop_table("certificates")
    op.drop_table("path_assignments")
    op.drop_table("path_versions")
    op.drop_table("cohort_members")
    op.drop_table("cohorts")
    op.drop_table("lesson_resources")
    op.drop_table("lesson_versions")
    op.drop_column("lessons", "unit_id")
    op.drop_table("course_units")
    for column in ("graded_at", "graded_by", "artifact_mime", "artifact", "feedback", "text_answer"):
        op.drop_column("attempts", column)
    for column in ("weight", "rubric", "due_at", "max_attempts", "correct_answer", "kind"):
        op.drop_column("activities", column)
    op.drop_constraint("uq_courses_institution_code", "courses", type_="unique")
    for column in ("certificate_signatory", "certificate_heading", "ends_at", "starts_at", "tags_json", "level", "code"):
        op.drop_column("courses", column)
    for column in ("published", "duration_hours", "prerequisites_json", "objective"):
        op.drop_column("learning_paths", column)

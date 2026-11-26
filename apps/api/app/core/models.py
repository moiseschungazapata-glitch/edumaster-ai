import uuid

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (CheckConstraint("role IN ('superadmin','admin','coordinator','teacher','student','analyst','ml_engineer','auditor')", name="valid_profile_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="student")
    institution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=True)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("institution_id", "code"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    level: Mapped[str] = mapped_column(String(24), nullable=False, default="beginner")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificate_heading: Mapped[str] = mapped_column(String(120), nullable=False, default="Certificado de finalización")
    certificate_signatory: Mapped[str] = mapped_column(String(120), nullable=False, default="EduMaster.ai")


class LearningPath(Base):
    __tablename__ = "learning_paths"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prerequisites_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PathAssignment(Base):
    __tablename__ = "path_assignments"
    __table_args__ = (UniqueConstraint("path_id", "student_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    target_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PathVersion(Base):
    __tablename__ = "path_versions"
    __table_args__ = (UniqueConstraint("path_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = (UniqueConstraint("institution_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class CohortMember(Base):
    __tablename__ = "cohort_members"
    __table_args__ = (UniqueConstraint("cohort_id", "student_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)


class PathCourse(Base):
    __tablename__ = "path_courses"
    __table_args__ = (UniqueConstraint("path_id", "course_id"), UniqueConstraint("path_id", "position"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class CourseUnit(Base):
    __tablename__ = "course_units"
    __table_args__ = (UniqueConstraint("course_id", "position"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("course_id", "position"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("course_units.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class LessonResource(Base):
    __tablename__ = "lesson_resources"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    artifact_mime: Mapped[str] = mapped_column(String(50), nullable=False, default="")


class LessonVersion(Base):
    __tablename__ = "lesson_versions"
    __table_args__ = (UniqueConstraint("lesson_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("course_id", "position"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="multiple_choice")
    correct_answer: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rubric: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("enrollment_id"), UniqueConstraint("verification_code"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id"), nullable=False)
    verification_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="issued")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("lesson_id", "enrollment_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    selected_index: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    text_answer: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    feedback: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    artifact_mime: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    graded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AcademicEvent(Base):
    __tablename__ = "academic_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    course_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AuditRecord(Base):
    __tablename__ = "audit_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "kind"),
        CheckConstraint("status IN ('new','accepted','discarded','completed','expired')", name="valid_recommendation_status"),
        CheckConstraint("review_status IN ('pending','approved','rejected')", name="valid_recommendation_review"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="academic-rules-v1")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id"), nullable=True)
    review_note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    feedback_useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

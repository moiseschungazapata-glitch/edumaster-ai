"""Institution-scoped academic workflows. The client never supplies identity or grades."""
import json
import base64
import binascii
import csv
import io
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from typing import Literal
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from app.core.db import get_db
from app.core.models import AcademicEvent, Activity, Attempt, Certificate, Cohort, CohortMember, Course, CourseUnit, Enrollment, LearningPath, Lesson, LessonProgress, LessonResource, LessonVersion, PathAssignment, PathCourse, Profile
from app.core.security import get_current_profile

router = APIRouter(tags=["academic"])
EDITORS = {"superadmin", "admin", "coordinator", "teacher"}


def record(db: Session, profile: Profile, kind: str, course_id: uuid.UUID | None = None):
    db.add(AcademicEvent(institution_id=institution(profile), actor_id=profile.id, course_id=course_id, kind=kind))
    from app.audit import record as audit_record
    audit_record(db, profile, kind, "course" if course_id else "learning_path", course_id)


class CourseInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=5000)
    code: str | None = Field(default=None, max_length=40)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    tags: list[str] = Field(default_factory=list, max_length=10)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    certificate_heading: str = Field(default="Certificado de finalización", min_length=3, max_length=120)
    certificate_signatory: str = Field(default="EduMaster.ai", min_length=2, max_length=120)


class PathInput(CourseInput):
    course_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    objective: str = Field(default="", max_length=2000)
    prerequisite_ids: list[uuid.UUID] = Field(default_factory=list, max_length=25)
    duration_hours: int = Field(default=0, ge=0, le=10000)


class LessonInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(min_length=1, max_length=20000)
    unit_id: uuid.UUID | None = None


class UnitInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)


class ResourceInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    url: HttpUrl


class ResourceFileInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    artifact_base64: str = Field(min_length=1, max_length=1_400_000)
    artifact_mime: str = Field(max_length=50)


def decode_academic_file(encoded: str, mime: str) -> bytes:
    if mime not in {"application/pdf", "image/png", "image/jpeg"}:
        raise HTTPException(422, "Solo se aceptan PDF, PNG y JPEG")
    try:
        artifact = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "Archivo inválido") from exc
    if len(artifact) > 1_000_000 or not artifact or not ((mime == "application/pdf" and artifact.startswith(b"%PDF-")) or (mime == "image/png" and artifact.startswith(b"\x89PNG\r\n\x1a\n")) or (mime == "image/jpeg" and artifact.startswith(b"\xff\xd8\xff"))):
        raise HTTPException(422, "Archivo inválido o mayor a 1 MB")
    return artifact


class ActivityInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    question: str = Field(min_length=2, max_length=2000)
    kind: Literal["multiple_choice", "true_false", "short_answer", "practical", "file_upload"] = "multiple_choice"
    options: list[str] = Field(default_factory=list, max_length=6)
    correct_index: int = Field(default=0, ge=0, le=5)
    correct_answer: str = Field(default="", max_length=500)
    max_attempts: int = Field(default=3, ge=1, le=20)
    passing_score: int = Field(default=100, ge=1, le=100)
    due_at: datetime | None = None
    rubric: str = Field(default="", max_length=2000)
    weight: int = Field(default=1, ge=1, le=100)


class AnswerInput(BaseModel):
    selected_index: int | None = Field(default=None, ge=0, le=5)
    text_answer: str = Field(default="", max_length=500)
    artifact_base64: str = Field(default="", max_length=1_400_000)
    artifact_mime: str = Field(default="", max_length=50)


class GradeInput(BaseModel):
    score: int = Field(ge=0, le=100)
    feedback: str = Field(default="", max_length=1000)


class AssignPathInput(BaseModel):
    student_id: uuid.UUID


class CohortInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class CohortStudentInput(BaseModel):
    student_id: uuid.UUID


class EnrollCohortInput(BaseModel):
    cohort_id: uuid.UUID


class AssignTeacherInput(BaseModel):
    teacher_id: uuid.UUID


class ImportCoursesInput(BaseModel):
    csv_text: str = Field(min_length=1, max_length=100000)


class CopyQuestionInput(BaseModel):
    activity_id: uuid.UUID


def institution(profile: Profile) -> uuid.UUID:
    if profile.role not in EDITORS | {"student"}:
        raise HTTPException(403, "Tu rol no tiene acceso al núcleo académico")
    if profile.institution_id is None:
        raise HTTPException(403, "Asigna una institución al perfil antes de usar cursos")
    return profile.institution_id


def editor(profile: Profile):
    if profile.role not in EDITORS:
        raise HTTPException(403, "Se requiere un rol docente o coordinador")
    institution(profile)


def course_or_404(db: Session, profile: Profile, course_id: uuid.UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.institution_id != institution(profile):
        raise HTTPException(404, "Curso no encontrado")
    if profile.role == "student" and not course.published:
        raise HTTPException(404, "Curso no encontrado")
    if profile.role == "teacher" and course.teacher_id != profile.id:
        raise HTTPException(404, "Curso no encontrado")
    return course


def can_edit(profile: Profile, course: Course):
    editor(profile)
    if profile.role == "teacher" and course.teacher_id != profile.id:
        raise HTTPException(403, "Solo el docente del curso puede modificarlo")


def enrollment_or_403(db: Session, profile: Profile, course: Course) -> Enrollment:
    if profile.role != "student":
        raise HTTPException(403, "Esta acción requiere un estudiante")
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id))
    if not enrollment:
        raise HTTPException(403, "Inscríbete antes de continuar")
    return enrollment


def progress(db: Session, enrollment: Enrollment, lessons: list[Lesson], activities: list[Activity]) -> dict:
    done = set(db.scalars(select(LessonProgress.lesson_id).where(LessonProgress.enrollment_id == enrollment.id)).all())
    passed = set(db.scalars(select(Attempt.activity_id).join(Activity, Activity.id == Attempt.activity_id).where(Attempt.enrollment_id == enrollment.id, Attempt.score >= Activity.passing_score)).all())
    total = len(lessons) + sum(activity.weight for activity in activities)
    earned = len(done) + sum(activity.weight for activity in activities if activity.id in passed)
    return {"completed_lesson_ids": list(done), "passed_activity_ids": list(passed), "percent": round(100 * earned / total) if total else 0, "completed": bool(total and len(done) == len(lessons) and len(passed) == len(activities))}


def issue_certificate_if_completed(db: Session, profile: Profile, course: Course, enrollment: Enrollment):
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id)))
    if not progress(db, enrollment, lessons, activities)["completed"]:
        return
    existing = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
    if existing is None:
        db.add(Certificate(enrollment_id=enrollment.id, verification_code=secrets.token_urlsafe(24)))
        record(db, profile, "certificate_issued", course.id)


def summary(db: Session, course: Course, profile: Profile) -> dict:
    enrolled = db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id)) if profile.role == "student" else None
    return {"id": course.id, "title": course.title, "description": course.description, "code": course.code, "level": course.level, "tags": json.loads(course.tags_json), "starts_at": course.starts_at, "ends_at": course.ends_at, "certificate_heading": course.certificate_heading, "certificate_signatory": course.certificate_signatory, "published": course.published, "teacher_id": course.teacher_id, "enrolled": bool(enrolled), "enrollment_count": db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == course.id)) if profile.role in EDITORS else None}


def validate_course_metadata(data: CourseInput):
    if len(data.title.strip()) < 2 or (data.code is not None and data.code.strip() and len(data.code.strip()) < 2):
        raise HTTPException(422, "Título o código demasiado corto")
    if any(not tag.strip() or len(tag) > 40 for tag in data.tags):
        raise HTTPException(422, "Las etiquetas deben tener entre 1 y 40 caracteres")
    for value in (data.starts_at, data.ends_at):
        if value is not None and value.tzinfo is None:
            raise HTTPException(422, "Las fechas requieren zona horaria")
    if data.starts_at and data.ends_at and data.ends_at <= data.starts_at:
        raise HTTPException(422, "La fecha de cierre debe ser posterior al inicio")
    if len(data.certificate_heading.strip()) < 3 or len(data.certificate_signatory.strip()) < 2:
        raise HTTPException(422, "Completa el título y el firmante del certificado")


@router.get("/courses")
def courses(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    stmt = select(Course).where(Course.institution_id == institution(profile)).order_by(Course.title)
    if profile.role == "student":
        stmt = stmt.where(Course.published.is_(True))
    elif profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    return [summary(db, course, profile) for course in db.scalars(stmt)]


@router.get("/courses/export.csv")
def export_courses(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    stmt = select(Course).where(Course.institution_id == institution(profile)).order_by(Course.title)
    if profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["code", "title", "description", "level", "tags", "published"])
    for course in db.scalars(stmt):
        values = [course.code or "", course.title, course.description, course.level, "|".join(json.loads(course.tags_json)), str(course.published).lower()]
        writer.writerow(["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
    record(db, profile, "courses_exported")
    db.commit()
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="cursos.csv"', "Cache-Control": "no-store"})


@router.post("/courses/import.csv")
def import_courses(data: ImportCoursesInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if profile.role not in {"superadmin", "admin", "coordinator"}:
        raise HTTPException(403, "La institución importa cursos")
    reader = csv.DictReader(io.StringIO(data.csv_text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"code", "title", "description", "level", "tags"}.issubset(set(reader.fieldnames)):
        raise HTTPException(422, "CSV: se requieren code,title,description,level,tags")
    rows = []
    seen = set()
    try:
        for index, row in enumerate(reader, 2):
            if index > 101:
                raise HTTPException(422, "Máximo 100 cursos por importación")
            payload = CourseInput(code=row["code"] or None, title=row["title"], description=row["description"], level=row["level"], tags=[tag.strip() for tag in row["tags"].split("|") if tag.strip()])
            validate_course_metadata(payload)
            code = payload.code.strip().upper() if payload.code else None
            if code and (code in seen or db.scalar(select(Course.id).where(Course.institution_id == institution(profile), Course.code == code))):
                raise HTTPException(409, f"Código duplicado en la fila {index}")
            if code:
                seen.add(code)
            rows.append(Course(institution_id=institution(profile), teacher_id=profile.id, code=code, title=payload.title.strip(), description=payload.description.strip(), level=payload.level, tags_json=json.dumps(payload.tags)))
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(422, "CSV inválido") from exc
    if not rows:
        raise HTTPException(422, "CSV sin cursos")
    db.add_all(rows)
    record(db, profile, "courses_imported")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Código de curso duplicado") from exc
    return {"created": len(rows)}


@router.post("/courses", status_code=201)
def create_course(data: CourseInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    validate_course_metadata(data)
    code = data.code.strip().upper() if data.code and data.code.strip() else None
    course = Course(institution_id=institution(profile), teacher_id=profile.id, title=data.title.strip(), description=data.description.strip(), code=code, level=data.level, tags_json=json.dumps([tag.strip() for tag in data.tags]), starts_at=data.starts_at, ends_at=data.ends_at, certificate_heading=data.certificate_heading.strip(), certificate_signatory=data.certificate_signatory.strip())
    if code and db.scalar(select(Course.id).where(Course.institution_id == course.institution_id, Course.code == code)):
        raise HTTPException(409, "Ya existe un curso con ese código")
    db.add(course)
    db.flush()
    record(db, profile, "course_created", course.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ya existe un curso con ese código") from exc
    db.refresh(course)
    return summary(db, course, profile)


@router.get("/courses/{course_id}")
def course_detail(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id)) if profile.role == "student" else None
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id).order_by(Lesson.position)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id).order_by(Activity.position)))
    result = summary(db, course, profile)
    result["units"] = [{"id": unit.id, "title": unit.title, "position": unit.position} for unit in db.scalars(select(CourseUnit).where(CourseUnit.course_id == course.id).order_by(CourseUnit.position))] if enrollment or profile.role in EDITORS else []
    result["lessons"] = [{"id": item.id, "unit_id": item.unit_id, "title": item.title, "content": item.content, "position": item.position, "resources": [{"id": resource.id, "title": resource.title, "url": resource.url, "has_file": bool(resource.artifact_mime)} for resource in db.scalars(select(LessonResource).options(defer(LessonResource.artifact)).where(LessonResource.lesson_id == item.id))]} for item in lessons] if enrollment or profile.role in EDITORS else []
    result["activities"] = [{"id": item.id, "title": item.title, "question": item.question, "kind": item.kind, "options": json.loads(item.options_json), "position": item.position, "max_attempts": item.max_attempts, "passing_score": item.passing_score, "weight": item.weight, "due_at": item.due_at, "rubric": item.rubric, **({"correct_index": item.correct_index, "correct_answer": item.correct_answer} if profile.role in EDITORS else {})} for item in activities] if enrollment or profile.role in EDITORS else []
    result["progress"] = progress(db, enrollment, lessons, activities) if enrollment else None
    if enrollment:
        certificate = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
        result["certificate"] = {"id": certificate.id, "status": certificate.status} if certificate else None
    return result


@router.patch("/courses/{course_id}")
def edit_course(course_id: uuid.UUID, data: CourseInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    validate_course_metadata(data)
    course.title, course.description = data.title.strip(), data.description.strip()
    fields = data.model_fields_set
    if "code" in fields:
        course.code = data.code.strip().upper() if data.code and data.code.strip() else None
        if course.code:
            with db.no_autoflush:
                if db.scalar(select(Course.id).where(Course.institution_id == course.institution_id, Course.code == course.code, Course.id != course.id)):
                    raise HTTPException(409, "Ya existe un curso con ese código")
    if "level" in fields:
        course.level = data.level
    if "tags" in fields:
        course.tags_json = json.dumps([tag.strip() for tag in data.tags])
    if "starts_at" in fields:
        course.starts_at = data.starts_at
    if "ends_at" in fields:
        course.ends_at = data.ends_at
    if "certificate_heading" in fields:
        course.certificate_heading = data.certificate_heading.strip()
    if "certificate_signatory" in fields:
        course.certificate_signatory = data.certificate_signatory.strip()
    if course.starts_at and course.ends_at and course.ends_at <= course.starts_at:
        raise HTTPException(422, "La fecha de cierre debe ser posterior al inicio")
    record(db, profile, "course_updated", course.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ya existe un curso con ese código") from exc
    return summary(db, course, profile)


@router.get("/teachers")
def teachers(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    return [{"id": user.id, "email": user.email} for user in db.scalars(select(Profile).where(Profile.institution_id == institution(profile), Profile.role == "teacher").order_by(Profile.email))]


@router.patch("/courses/{course_id}/teacher")
def assign_teacher(course_id: uuid.UUID, data: AssignTeacherInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if profile.role not in {"superadmin", "admin", "coordinator"}:
        raise HTTPException(403, "La institución asigna docentes")
    course = course_or_404(db, profile, course_id)
    assigned = db.get(Profile, data.teacher_id)
    if assigned is None or assigned.institution_id != institution(profile) or assigned.role != "teacher":
        raise HTTPException(404, "Docente no encontrado")
    course.teacher_id = assigned.id
    record(db, profile, "teacher_assigned", course.id)
    db.commit()
    return summary(db, course, profile)


@router.post("/courses/{course_id}/publish")
def publish(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if not db.scalar(select(Lesson.id).where(Lesson.course_id == course_id).limit(1)):
        raise HTTPException(409, "Añade al menos una lección antes de publicar")
    course.published = True
    record(db, profile, "course_published", course.id)
    db.commit()
    return summary(db, course, profile)


@router.post("/courses/{course_id}/unpublish")
def unpublish(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if db.scalar(select(Enrollment.id).where(Enrollment.course_id == course_id).limit(1)):
        raise HTTPException(409, "No puedes cambiar un curso con estudiantes inscritos")
    course.published = False
    record(db, profile, "course_unpublished", course.id)
    db.commit()
    return summary(db, course, profile)


@router.post("/courses/{course_id}/lessons", status_code=201)
def add_lesson(course_id: uuid.UUID, data: LessonInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de cambiar su contenido")
    if data.unit_id and not db.scalar(select(CourseUnit.id).where(CourseUnit.id == data.unit_id, CourseUnit.course_id == course.id)):
        raise HTTPException(404, "Unidad no encontrada")
    position = (db.scalar(select(func.max(Lesson.position)).where(Lesson.course_id == course_id)) or 0) + 1
    lesson = Lesson(course_id=course_id, unit_id=data.unit_id, title=data.title.strip(), content=data.content.strip(), position=position)
    db.add(lesson)
    db.flush()
    db.add(LessonVersion(lesson_id=lesson.id, version=1, title=lesson.title, content=lesson.content, changed_by=profile.id))
    record(db, profile, "lesson_created", course_id)
    db.commit()
    return {"id": lesson.id, "position": position}


@router.post("/courses/{course_id}/units", status_code=201)
def add_unit(course_id: uuid.UUID, data: UnitInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de cambiar sus unidades")
    position = (db.scalar(select(func.max(CourseUnit.position)).where(CourseUnit.course_id == course_id)) or 0) + 1
    unit = CourseUnit(course_id=course.id, title=data.title.strip(), position=position)
    db.add(unit)
    record(db, profile, "unit_created", course_id)
    db.commit()
    return {"id": unit.id, "title": unit.title, "position": position}


def draft_lesson(db: Session, profile: Profile, course_id: uuid.UUID, lesson_id: uuid.UUID):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de editar lecciones")
    lesson = db.scalar(select(Lesson).where(Lesson.id == lesson_id, Lesson.course_id == course.id))
    if lesson is None:
        raise HTTPException(404, "Lección no encontrada")
    return lesson


@router.patch("/courses/{course_id}/lessons/{lesson_id}")
def edit_lesson(course_id: uuid.UUID, lesson_id: uuid.UUID, data: LessonInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    lesson = draft_lesson(db, profile, course_id, lesson_id)
    if data.unit_id and not db.scalar(select(CourseUnit.id).where(CourseUnit.id == data.unit_id, CourseUnit.course_id == course_id)):
        raise HTTPException(404, "Unidad no encontrada")
    last = db.scalar(select(func.max(LessonVersion.version)).where(LessonVersion.lesson_id == lesson.id)) or 0
    if not last:
        db.add(LessonVersion(lesson_id=lesson.id, version=1, title=lesson.title, content=lesson.content, changed_by=profile.id))
    lesson.title, lesson.content = data.title.strip(), data.content.strip()
    if "unit_id" in data.model_fields_set:
        lesson.unit_id = data.unit_id
    db.add(LessonVersion(lesson_id=lesson.id, version=last + 1 if last else 2, title=lesson.title, content=lesson.content, changed_by=profile.id))
    record(db, profile, "lesson_updated", course_id)
    db.commit()
    return {"id": lesson.id, "title": lesson.title}


@router.get("/courses/{course_id}/lessons/{lesson_id}/versions")
def lesson_versions(course_id: uuid.UUID, lesson_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if not db.scalar(select(Lesson.id).where(Lesson.id == lesson_id, Lesson.course_id == course_id)):
        raise HTTPException(404, "Lección no encontrada")
    return [{"version": version.version, "title": version.title, "content": version.content, "changed_at": version.changed_at} for version in db.scalars(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id).order_by(LessonVersion.version.desc()))]


@router.post("/courses/{course_id}/lessons/{lesson_id}/restore/{version_number}")
def restore_lesson(course_id: uuid.UUID, lesson_id: uuid.UUID, version_number: int, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    lesson = draft_lesson(db, profile, course_id, lesson_id)
    prior = db.scalar(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id, LessonVersion.version == version_number))
    if prior is None:
        raise HTTPException(404, "Versión no encontrada")
    current = db.scalar(select(func.max(LessonVersion.version)).where(LessonVersion.lesson_id == lesson.id)) or 0
    lesson.title, lesson.content = prior.title, prior.content
    db.add(LessonVersion(lesson_id=lesson.id, version=current + 1, title=lesson.title, content=lesson.content, changed_by=profile.id))
    record(db, profile, "lesson_restored", course_id)
    db.commit()
    return {"id": lesson.id, "version": current + 1}


@router.post("/courses/{course_id}/lessons/{lesson_id}/resources", status_code=201)
def add_lesson_resource(course_id: uuid.UUID, lesson_id: uuid.UUID, data: ResourceInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    draft_lesson(db, profile, course_id, lesson_id)
    if data.url.scheme != "https":
        raise HTTPException(422, "Los recursos deben utilizar HTTPS")
    resource = LessonResource(lesson_id=lesson_id, title=data.title.strip(), url=str(data.url))
    db.add(resource)
    record(db, profile, "resource_created", course_id)
    db.commit()
    return {"id": resource.id, "title": resource.title, "url": resource.url}


@router.post("/courses/{course_id}/lessons/{lesson_id}/files", status_code=201)
def add_lesson_file(course_id: uuid.UUID, lesson_id: uuid.UUID, data: ResourceFileInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    draft_lesson(db, profile, course_id, lesson_id)
    artifact = decode_academic_file(data.artifact_base64, data.artifact_mime)
    resource = LessonResource(lesson_id=lesson_id, title=data.title.strip(), url="", artifact=artifact, artifact_mime=data.artifact_mime)
    db.add(resource)
    record(db, profile, "resource_created", course_id)
    db.commit()
    return {"id": resource.id, "title": resource.title, "has_file": True}


@router.get("/courses/{course_id}/lessons/{lesson_id}/resources/{resource_id}/file")
def download_lesson_file(course_id: uuid.UUID, lesson_id: uuid.UUID, resource_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    if profile.role == "student":
        enrollment_or_403(db, profile, course)
    if not db.scalar(select(Lesson.id).where(Lesson.id == lesson_id, Lesson.course_id == course_id)):
        raise HTTPException(404, "Lección no encontrada")
    resource = db.scalar(select(LessonResource).where(LessonResource.id == resource_id, LessonResource.lesson_id == lesson_id))
    if resource is None or not resource.artifact:
        raise HTTPException(404, "Archivo no encontrado")
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(resource.artifact_mime, "bin")
    record(db, profile, "resource_downloaded", course.id)
    db.commit()
    return Response(resource.artifact, media_type=resource.artifact_mime, headers={"Content-Disposition": f'attachment; filename="recurso-{resource.id}.{extension}"', "Cache-Control": "no-store"})


@router.delete("/courses/{course_id}/lessons/{lesson_id}/resources/{resource_id}")
def remove_lesson_resource(course_id: uuid.UUID, lesson_id: uuid.UUID, resource_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    draft_lesson(db, profile, course_id, lesson_id)
    resource = db.scalar(select(LessonResource).where(LessonResource.id == resource_id, LessonResource.lesson_id == lesson_id))
    if resource is None:
        raise HTTPException(404, "Recurso no encontrado")
    db.delete(resource)
    record(db, profile, "resource_deleted", course_id)
    db.commit()
    return {"status": "deleted"}


@router.post("/courses/{course_id}/activities", status_code=201)
def add_activity(course_id: uuid.UUID, data: ActivityInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de cambiar su evaluación")
    if data.kind == "multiple_choice" and (len(data.options) < 2 or data.correct_index >= len(data.options) or any(not option.strip() for option in data.options)):
        raise HTTPException(422, "Opciones o respuesta correcta inválidas")
    if data.kind == "true_false" and data.correct_index not in (0, 1):
        raise HTTPException(422, "Respuesta verdadero/falso inválida")
    if data.kind == "short_answer" and not data.correct_answer.strip():
        raise HTTPException(422, "Define la respuesta esperada")
    if data.kind in {"practical", "file_upload"} and not data.rubric.strip():
        raise HTTPException(422, "Define los criterios de revisión")
    if data.due_at and (data.due_at.tzinfo is None or data.due_at <= datetime.now(timezone.utc)):
        raise HTTPException(422, "La fecha límite debe ser futura y tener zona horaria")
    position = (db.scalar(select(func.max(Activity.position)).where(Activity.course_id == course_id)) or 0) + 1
    options = [option.strip() for option in data.options] if data.kind == "multiple_choice" else ["Verdadero", "Falso"] if data.kind == "true_false" else []
    activity = Activity(course_id=course_id, title=data.title.strip(), question=data.question.strip(), kind=data.kind, options_json=json.dumps(options), correct_index=data.correct_index, correct_answer=data.correct_answer.strip() if data.kind == "short_answer" else "", max_attempts=data.max_attempts, passing_score=data.passing_score, weight=data.weight, due_at=data.due_at, rubric=data.rubric.strip(), position=position)
    db.add(activity)
    record(db, profile, "activity_created", course_id)
    db.commit()
    return {"id": activity.id, "position": position}


@router.get("/question-bank")
def question_bank(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    stmt = select(Activity, Course).join(Course, Activity.course_id == Course.id).where(Course.institution_id == institution(profile)).order_by(Course.title, Activity.title)
    if profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    return [{"id": activity.id, "course_id": course.id, "course_title": course.title, "title": activity.title, "kind": activity.kind, "question": activity.question} for activity, course in db.execute(stmt)]


@router.post("/courses/{course_id}/activities/from-bank", status_code=201)
def copy_question(course_id: uuid.UUID, data: CopyQuestionInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    target = course_or_404(db, profile, course_id)
    can_edit(profile, target)
    if target.published:
        raise HTTPException(409, "Despublica el curso antes de copiar evaluaciones")
    source = db.scalar(select(Activity).join(Course, Activity.course_id == Course.id).where(Activity.id == data.activity_id, Course.institution_id == institution(profile)))
    if source is None:
        raise HTTPException(404, "Pregunta no encontrada")
    source_course = course_or_404(db, profile, source.course_id)
    position = (db.scalar(select(func.max(Activity.position)).where(Activity.course_id == course_id)) or 0) + 1
    copied = Activity(course_id=target.id, title=source.title, question=source.question, options_json=source.options_json, correct_index=source.correct_index, passing_score=source.passing_score, weight=source.weight, position=position, kind=source.kind, correct_answer=source.correct_answer, max_attempts=source.max_attempts, rubric=source.rubric, due_at=None)
    db.add(copied)
    record(db, profile, "assessment_copied", target.id)
    db.commit()
    return {"id": copied.id, "source_course_id": source_course.id}


@router.post("/courses/{course_id}/enroll", status_code=201)
def enroll(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    if profile.role != "student":
        raise HTTPException(403, "Solo estudiantes pueden matricularse")
    assigned_paths = list(db.scalars(select(LearningPath).join(PathCourse, PathCourse.path_id == LearningPath.id).join(PathAssignment, PathAssignment.path_id == LearningPath.id).where(PathCourse.course_id == course.id, PathAssignment.student_id == profile.id, LearningPath.published.is_(True))))
    if assigned_paths:
        def eligible(path: LearningPath) -> bool:
            for prerequisite_id in json.loads(path.prerequisites_json):
                if uuid.UUID(prerequisite_id) == course.id:
                    continue
                prerequisite = db.scalar(select(Enrollment).where(Enrollment.student_id == profile.id, Enrollment.course_id == uuid.UUID(prerequisite_id)))
                if prerequisite is None or not progress(db, prerequisite, list(db.scalars(select(Lesson).where(Lesson.course_id == prerequisite.course_id))), list(db.scalars(select(Activity).where(Activity.course_id == prerequisite.course_id))))["completed"]:
                    return False
            return True
        if not any(eligible(path) for path in assigned_paths):
            raise HTTPException(409, "Completa los cursos prerrequisito de tu ruta antes de matricularte")
    if course.starts_at and course.starts_at.replace(tzinfo=course.starts_at.tzinfo or timezone.utc) > datetime.now(timezone.utc):
        raise HTTPException(409, "El curso aún no está abierto")
    if course.ends_at and course.ends_at.replace(tzinfo=course.ends_at.tzinfo or timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(409, "El periodo de inscripción terminó")
    if db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id)):
        raise HTTPException(409, "Ya estás matriculado")
    db.add(Enrollment(course_id=course.id, student_id=profile.id))
    record(db, profile, "enrolled", course.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ya estás matriculado") from exc
    return {"status": "enrolled"}


@router.post("/courses/{course_id}/lessons/{lesson_id}/complete")
def complete_lesson(course_id: uuid.UUID, lesson_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = enrollment_or_403(db, profile, course)
    if not db.scalar(select(Lesson.id).where(Lesson.id == lesson_id, Lesson.course_id == course_id)):
        raise HTTPException(404, "Lección no encontrada")
    if not db.scalar(select(LessonProgress.id).where(LessonProgress.lesson_id == lesson_id, LessonProgress.enrollment_id == enrollment.id)):
        db.add(LessonProgress(lesson_id=lesson_id, enrollment_id=enrollment.id))
        record(db, profile, "lesson_completed", course.id)
        try:
            db.flush()
            issue_certificate_if_completed(db, profile, course, enrollment)
            db.commit()
        except IntegrityError:
            db.rollback()  # Idempotent if a second request completed the lesson concurrently.
    return {"status": "completed"}


@router.post("/courses/{course_id}/activities/{activity_id}/attempts", status_code=201)
def submit_answer(course_id: uuid.UUID, activity_id: uuid.UUID, data: AnswerInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = enrollment_or_403(db, profile, course)
    activity = db.scalar(select(Activity).where(Activity.id == activity_id, Activity.course_id == course_id))
    if not activity:
        raise HTTPException(404, "Actividad no encontrada")
    if activity.due_at and activity.due_at.replace(tzinfo=activity.due_at.tzinfo or timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(409, "La evaluación ya cerró")
    count = db.scalar(select(func.count(Attempt.id)).where(Attempt.enrollment_id == enrollment.id, Attempt.activity_id == activity.id))
    if count >= activity.max_attempts:
        raise HTTPException(409, "Has alcanzado el límite de intentos")
    artifact = None
    if activity.kind == "file_upload":
        artifact = decode_academic_file(data.artifact_base64, data.artifact_mime)
        score, selected, response = -1, 0, data.text_answer.strip()
    elif activity.kind == "practical":
        response = data.text_answer.strip()
        if not response:
            raise HTTPException(422, "Describe tu trabajo")
        score, selected = -1, 0
    elif activity.kind == "short_answer":
        response = data.text_answer.strip()
        if not response:
            raise HTTPException(422, "Escribe una respuesta")
        score = 100 if response.casefold() == activity.correct_answer.casefold() else 0
        selected = 0
    else:
        if data.selected_index is None or data.selected_index >= len(json.loads(activity.options_json)):
            raise HTTPException(422, "Opción inválida")
        score = 100 if data.selected_index == activity.correct_index else 0
        selected = data.selected_index
        response = ""
    attempt = Attempt(activity_id=activity_id, enrollment_id=enrollment.id, selected_index=selected, text_answer=response, score=score, artifact=artifact, artifact_mime=data.artifact_mime if artifact else "")
    db.add(attempt)
    record(db, profile, "assessment_submitted" if score < 0 else "assessment_passed" if score >= activity.passing_score else "assessment_failed", course.id)
    db.flush()
    issue_certificate_if_completed(db, profile, course, enrollment)
    db.commit()
    return {"id": attempt.id, "score": score if score >= 0 else None, "passed": score >= activity.passing_score, "pending_review": score < 0}


@router.get("/courses/{course_id}/attempts")
def my_attempts(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = enrollment_or_403(db, profile, course)
    return [{"id": a.id, "activity_id": a.activity_id, "score": a.score if a.score >= 0 else None, "selected_index": a.selected_index, "text_answer": a.text_answer, "feedback": a.feedback, "has_artifact": bool(a.artifact_mime)} for a in db.scalars(select(Attempt).options(defer(Attempt.artifact)).join(Activity).where(Attempt.enrollment_id == enrollment.id, Activity.course_id == course.id))]


@router.get("/courses/{course_id}/students/progress")
def course_student_progress(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    editor(profile)
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id)))
    result = []
    for enrollment, student in db.execute(select(Enrollment, Profile).join(Profile, Enrollment.student_id == Profile.id).where(Enrollment.course_id == course.id).order_by(Profile.email)):
        attempts = db.scalars(select(Attempt).options(defer(Attempt.artifact)).join(Activity, Activity.id == Attempt.activity_id).where(Attempt.enrollment_id == enrollment.id, Activity.course_id == course.id)).all()
        result.append({"student_id": student.id, "email": student.email, "enrolled_at": enrollment.created_at, "progress": progress(db, enrollment, lessons, activities), "attempts": [{"activity_id": attempt.activity_id, "score": attempt.score, "created_at": attempt.created_at} for attempt in attempts]})
    return result


@router.get("/courses/{course_id}/submissions")
def course_submissions(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    editor(profile)
    rows = db.execute(select(Attempt, Activity, Profile).options(defer(Attempt.artifact)).join(Activity, Activity.id == Attempt.activity_id).join(Enrollment, Enrollment.id == Attempt.enrollment_id).join(Profile, Profile.id == Enrollment.student_id).where(Activity.course_id == course.id, Activity.kind.in_(["file_upload", "practical"])).order_by(Attempt.created_at.desc())).all()
    return [{"id": attempt.id, "activity_title": activity.title, "student_email": student.email, "text_answer": attempt.text_answer, "has_artifact": bool(attempt.artifact_mime), "score": attempt.score if attempt.score >= 0 else None, "feedback": attempt.feedback, "submitted_at": attempt.created_at} for attempt, activity, student in rows]


def attempt_for_user(db: Session, profile: Profile, course_id: uuid.UUID, attempt_id: uuid.UUID):
    course = course_or_404(db, profile, course_id)
    row = db.execute(select(Attempt, Enrollment, Activity).join(Enrollment, Attempt.enrollment_id == Enrollment.id).join(Activity, Attempt.activity_id == Activity.id).where(Attempt.id == attempt_id, Activity.course_id == course.id)).first()
    if row is None:
        raise HTTPException(404, "Entrega no encontrada")
    attempt, enrollment, _ = row
    if profile.role == "student" and enrollment.student_id != profile.id:
        raise HTTPException(404, "Entrega no encontrada")
    return course, attempt, enrollment


@router.get("/courses/{course_id}/submissions/{attempt_id}/file")
def download_submission(course_id: uuid.UUID, attempt_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course, attempt, _ = attempt_for_user(db, profile, course_id, attempt_id)
    if not attempt.artifact:
        raise HTTPException(404, "Archivo no encontrado")
    record(db, profile, "submission_downloaded", course.id)
    db.commit()
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(attempt.artifact_mime, "bin")
    return Response(attempt.artifact, media_type=attempt.artifact_mime, headers={"Content-Disposition": f'attachment; filename="entrega-{attempt.id}.{extension}"', "Cache-Control": "no-store"})


@router.post("/courses/{course_id}/submissions/{attempt_id}/grade")
def grade_submission(course_id: uuid.UUID, attempt_id: uuid.UUID, data: GradeInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course, attempt, enrollment = attempt_for_user(db, profile, course_id, attempt_id)
    can_edit(profile, course)
    activity = db.get(Activity, attempt.activity_id)
    if activity.kind not in {"practical", "file_upload"}:
        raise HTTPException(409, "Esta evaluación tiene calificación automática")
    attempt.score = data.score
    attempt.feedback = data.feedback.strip()
    attempt.graded_by = profile.id
    attempt.graded_at = datetime.now(timezone.utc)
    record(db, profile, "assessment_passed" if data.score >= activity.passing_score else "assessment_failed", course.id)
    db.flush()
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id)))
    if progress(db, enrollment, lessons, activities)["completed"]:
        issue_certificate_if_completed(db, profile, course, enrollment)
    else:
        certificate = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id, Certificate.status == "issued"))
        if certificate:
            certificate.status = "revoked"
            certificate.revoked_at = datetime.now(timezone.utc)
            record(db, profile, "certificate_revoked", course.id)
    db.commit()
    return {"score": attempt.score, "passed": attempt.score >= activity.passing_score}


@router.get("/paths")
def paths(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    result = []
    for path in db.scalars(select(LearningPath).where(LearningPath.institution_id == institution(profile)).order_by(LearningPath.title)):
        if profile.role == "student" and not path.published:
            continue
        entries = db.execute(select(PathCourse, Course).join(Course, PathCourse.course_id == Course.id).where(PathCourse.path_id == path.id).order_by(PathCourse.position)).all()
        visible = [course for _, course in entries if (course.published or profile.role in EDITORS) and (profile.role != "teacher" or course.teacher_id == profile.id)]
        if profile.role in {"student", "teacher"} and not visible:
            continue
        assigned = list(db.scalars(select(PathAssignment.student_id).where(PathAssignment.path_id == path.id)).all()) if profile.role in EDITORS else []
        mine = db.scalar(select(PathAssignment.id).where(PathAssignment.path_id == path.id, PathAssignment.student_id == profile.id)) if profile.role == "student" else None
        done = 0
        if mine:
            for course in visible:
                enrollment = db.scalar(select(Enrollment).where(Enrollment.student_id == profile.id, Enrollment.course_id == course.id))
                if enrollment and progress(db, enrollment, list(db.scalars(select(Lesson).where(Lesson.course_id == course.id))), list(db.scalars(select(Activity).where(Activity.course_id == course.id))))["completed"]:
                    done += 1
        prerequisites_met = True
        if profile.role == "student":
            for prerequisite_id in json.loads(path.prerequisites_json):
                prerequisite = db.scalar(select(Enrollment).where(Enrollment.course_id == uuid.UUID(prerequisite_id), Enrollment.student_id == profile.id))
                if prerequisite is None:
                    prerequisites_met = False
                    break
                prerequisite_lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == prerequisite.course_id)))
                prerequisite_activities = list(db.scalars(select(Activity).where(Activity.course_id == prerequisite.course_id)))
                if not progress(db, prerequisite, prerequisite_lessons, prerequisite_activities)["completed"]:
                    prerequisites_met = False
                    break
        result.append({"id": path.id, "title": path.title, "description": path.description, "objective": path.objective, "prerequisite_ids": json.loads(path.prerequisites_json), "prerequisites_met": prerequisites_met, "duration_hours": path.duration_hours, "published": path.published, "courses": [summary(db, course, profile) for course in visible], "assigned_student_ids": assigned, "assigned_to_me": bool(mine), "percent": round(100 * done / len(visible)) if mine and visible else 0})
    return result


@router.post("/paths", status_code=201)
def create_path(data: PathInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    if len(data.course_ids) != len(set(data.course_ids)) or len(data.prerequisite_ids) != len(set(data.prerequisite_ids)):
        raise HTTPException(422, "No repitas cursos en la ruta")
    for course_id in data.course_ids:
        course = course_or_404(db, profile, course_id)
        can_edit(profile, course)
    for prerequisite_id in data.prerequisite_ids:
        prerequisite = course_or_404(db, profile, prerequisite_id)
        if not prerequisite.published:
            raise HTTPException(409, "Publica los cursos prerrequisito antes de usar la ruta")
    path = LearningPath(institution_id=institution(profile), title=data.title.strip(), description=data.description.strip(), objective=data.objective.strip(), prerequisites_json=json.dumps([str(item) for item in data.prerequisite_ids]), duration_hours=data.duration_hours, published=False)
    db.add(path)
    db.flush()
    for position, course_id in enumerate(data.course_ids, 1):
        db.add(PathCourse(path_id=path.id, course_id=course_id, position=position))
    record(db, profile, "path_created")
    db.commit()
    return {"id": path.id, "title": path.title}


@router.post("/paths/{path_id}/publish")
def publish_path(path_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    path = db.get(LearningPath, path_id)
    if path is None or path.institution_id != institution(profile):
        raise HTTPException(404, "Ruta no encontrada")
    entries = list(db.scalars(select(Course).join(PathCourse, Course.id == PathCourse.course_id).where(PathCourse.path_id == path_id)))
    if not entries or any(not course.published or (profile.role == "teacher" and course.teacher_id != profile.id) for course in entries):
        raise HTTPException(409, "Publica los cursos de esta ruta antes de publicarla")
    path.published = True
    record(db, profile, "path_published")
    db.commit()
    return {"status": "published"}


@router.post("/paths/{path_id}/assign-cohort")
def assign_path_cohort(path_id: uuid.UUID, data: EnrollCohortInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if profile.role not in {"superadmin", "admin", "coordinator"}:
        raise HTTPException(403, "La institución asigna rutas a cohortes")
    path = db.get(LearningPath, path_id)
    if path is None or path.institution_id != institution(profile):
        raise HTTPException(404, "Ruta no encontrada")
    if not path.published:
        raise HTTPException(409, "Publica la ruta antes de asignarla")
    cohort = cohort_or_404(db, profile, data.cohort_id)
    members = list(db.scalars(select(CohortMember.student_id).join(Profile, CohortMember.student_id == Profile.id).where(CohortMember.cohort_id == cohort.id, Profile.role == "student", Profile.institution_id == institution(profile))))
    existing = set(db.scalars(select(PathAssignment.student_id).where(PathAssignment.path_id == path.id)))
    for student_id in members:
        if student_id not in existing:
            db.add(PathAssignment(path_id=path.id, student_id=student_id))
    inserted = len(set(members) - existing)
    if inserted:
        record(db, profile, "path_assigned")
    db.commit()
    return {"assigned": inserted, "already_assigned": len(members) - inserted}


@router.get("/students")
def students(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    query = select(Profile).where(Profile.institution_id == institution(profile), Profile.role == "student").order_by(Profile.email)
    if profile.role == "teacher":
        query = query.join(Enrollment, Enrollment.student_id == Profile.id).join(Course, Course.id == Enrollment.course_id).where(Course.teacher_id == profile.id).distinct()
    return [{"id": user.id, "email": user.email} for user in db.scalars(query)]


def cohort_or_404(db: Session, profile: Profile, cohort_id: uuid.UUID) -> Cohort:
    editor(profile)
    if profile.role == "teacher":
        raise HTTPException(403, "La institución administra las cohortes")
    cohort = db.get(Cohort, cohort_id)
    if cohort is None or cohort.institution_id != institution(profile):
        raise HTTPException(404, "Cohorte no encontrada")
    return cohort


@router.get("/cohorts")
def list_cohorts(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    if profile.role == "teacher":
        raise HTTPException(403, "La institución administra las cohortes")
    cohorts = db.scalars(select(Cohort).where(Cohort.institution_id == institution(profile)).order_by(Cohort.name))
    return [{"id": cohort.id, "name": cohort.name, "student_ids": list(db.scalars(select(CohortMember.student_id).where(CohortMember.cohort_id == cohort.id)))} for cohort in cohorts]


@router.post("/cohorts", status_code=201)
def create_cohort(data: CohortInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    if profile.role == "teacher":
        raise HTTPException(403, "La institución administra las cohortes")
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Nombre demasiado corto")
    if db.scalar(select(Cohort.id).where(Cohort.institution_id == institution(profile), Cohort.name == name)):
        raise HTTPException(409, "Ya existe una cohorte con ese nombre")
    cohort = Cohort(institution_id=institution(profile), name=name)
    db.add(cohort)
    record(db, profile, "cohort_created")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ya existe una cohorte con ese nombre") from exc
    return {"id": cohort.id, "name": name}


@router.post("/cohorts/{cohort_id}/students", status_code=201)
def add_cohort_student(cohort_id: uuid.UUID, data: CohortStudentInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    cohort_or_404(db, profile, cohort_id)
    if profile.role == "teacher":
        raise HTTPException(403, "La institución administra las cohortes")
    student = db.get(Profile, data.student_id)
    if student is None or student.institution_id != institution(profile) or student.role != "student":
        raise HTTPException(404, "Estudiante no encontrado")
    if profile.role == "teacher" and not db.scalar(select(Enrollment.id).join(Course, Enrollment.course_id == Course.id).where(Enrollment.student_id == student.id, Course.teacher_id == profile.id).limit(1)):
        raise HTTPException(404, "Estudiante no encontrado")
    if db.scalar(select(CohortMember.id).where(CohortMember.cohort_id == cohort_id, CohortMember.student_id == student.id)):
        raise HTTPException(409, "Estudiante ya asignado a esta cohorte")
    db.add(CohortMember(cohort_id=cohort_id, student_id=student.id))
    record(db, profile, "cohort_student_added")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Estudiante ya asignado a esta cohorte") from exc
    return {"status": "assigned"}


@router.post("/courses/{course_id}/enroll-cohort")
def enroll_cohort(course_id: uuid.UUID, data: EnrollCohortInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if profile.role == "teacher":
        raise HTTPException(403, "La institución matricula cohortes")
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if not course.published:
        raise HTTPException(409, "Publica el curso antes de matricular una cohorte")
    cohort = cohort_or_404(db, profile, data.cohort_id)
    members = list(db.scalars(select(CohortMember.student_id).join(Profile, CohortMember.student_id == Profile.id).where(CohortMember.cohort_id == cohort.id, Profile.institution_id == institution(profile), Profile.role == "student")))
    current = set(db.scalars(select(Enrollment.student_id).where(Enrollment.course_id == course.id)))
    for student_id in members:
        if student_id not in current:
            db.add(Enrollment(course_id=course.id, student_id=student_id))
            db.add(AcademicEvent(institution_id=institution(profile), actor_id=student_id, course_id=course.id, kind="enrolled"))
    inserted = len(set(members) - current)
    if inserted:
        record(db, profile, "cohort_enrolled", course.id)
    db.commit()
    return {"enrolled": inserted, "already_enrolled": len(members) - inserted}


@router.post("/paths/{path_id}/assign", status_code=201)
def assign_path(path_id: uuid.UUID, data: AssignPathInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    path = db.get(LearningPath, path_id)
    if path is None or path.institution_id != institution(profile):
        raise HTTPException(404, "Ruta no encontrada")
    if not path.published:
        raise HTTPException(409, "Publica la ruta antes de asignarla")
    if profile.role == "teacher":
        entries = list(db.scalars(select(Course).join(PathCourse, Course.id == PathCourse.course_id).where(PathCourse.path_id == path_id)))
        if not entries or any(course.teacher_id != profile.id for course in entries):
            raise HTTPException(403, "Solo puedes asignar rutas de tus cursos")
    student = db.get(Profile, data.student_id)
    if student is None or student.institution_id != institution(profile) or student.role != "student":
        raise HTTPException(404, "Estudiante no encontrado")
    if db.scalar(select(PathAssignment.id).where(PathAssignment.path_id == path_id, PathAssignment.student_id == student.id)):
        raise HTTPException(409, "La ruta ya está asignada")
    db.add(PathAssignment(path_id=path_id, student_id=student.id))
    record(db, profile, "path_assigned")
    db.commit()
    return {"status": "assigned"}


def certificate_for_user(db: Session, profile: Profile, certificate_id: uuid.UUID):
    row = db.execute(select(Certificate, Enrollment, Course).join(Enrollment, Certificate.enrollment_id == Enrollment.id).join(Course, Enrollment.course_id == Course.id).where(Certificate.id == certificate_id, Course.institution_id == institution(profile))).first()
    if row is None:
        raise HTTPException(404, "Certificado no encontrado")
    certificate, enrollment, course = row
    if profile.role == "student" and enrollment.student_id != profile.id:
        raise HTTPException(404, "Certificado no encontrado")
    if profile.role == "teacher" and course.teacher_id != profile.id:
        raise HTTPException(404, "Certificado no encontrado")
    return certificate, enrollment, course


@router.get("/certificates")
def list_certificates(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    stmt = select(Certificate, Enrollment, Course).join(Enrollment, Certificate.enrollment_id == Enrollment.id).join(Course, Enrollment.course_id == Course.id).where(Course.institution_id == institution(profile)).order_by(Certificate.issued_at.desc())
    if profile.role == "student":
        stmt = stmt.where(Enrollment.student_id == profile.id)
    elif profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    return [{"id": certificate.id, "course_id": course.id, "course_title": course.title, "status": certificate.status, "issued_at": certificate.issued_at, "student_id": enrollment.student_id if profile.role in EDITORS else None} for certificate, enrollment, course in db.execute(stmt)]


@router.post("/courses/{course_id}/certificate", status_code=201)
def claim_certificate(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = enrollment_or_403(db, profile, course)
    existing = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
    if existing:
        if existing.status != "issued":
            raise HTTPException(409, "El certificado fue anulado")
        return {"id": existing.id, "status": existing.status}
    issue_certificate_if_completed(db, profile, course, enrollment)
    certificate = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
    if not certificate:
        raise HTTPException(409, "Primero completa las lecciones y aprueba todas las evaluaciones")
    db.commit()
    return {"id": certificate.id, "status": certificate.status}


@router.get("/certificates/{certificate_id}/pdf")
def download_certificate(certificate_id: uuid.UUID, request: Request, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    certificate, enrollment, course = certificate_for_user(db, profile, certificate_id)
    if certificate.status != "issued":
        raise HTTPException(409, "Este certificado fue anulado")
    from app.certificate_pdf import render_certificate
    record(db, profile, "certificate_downloaded", course.id)
    db.commit()
    student = db.get(Profile, enrollment.student_id)
    verification_url = f"{str(request.base_url).rstrip('/')}/verify/{certificate.verification_code}"
    return Response(render_certificate(course.title, student.email, certificate.verification_code, certificate.issued_at, verification_url, course.certificate_heading, course.certificate_signatory), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="certificado-{certificate.id}.pdf"', "Cache-Control": "no-store"})


@router.post("/certificates/{certificate_id}/revoke")
def revoke_certificate(certificate_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    certificate, _, course = certificate_for_user(db, profile, certificate_id)
    can_edit(profile, course)
    if certificate.status != "issued":
        raise HTTPException(409, "Ya está anulado")
    certificate.status = "revoked"
    certificate.revoked_at = datetime.now(timezone.utc)
    record(db, profile, "certificate_revoked", course.id)
    db.commit()
    return {"status": "revoked"}


@router.post("/certificates/{certificate_id}/reissue")
def reissue_certificate(certificate_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    certificate, enrollment, course = certificate_for_user(db, profile, certificate_id)
    can_edit(profile, course)
    if certificate.status != "revoked":
        raise HTTPException(409, "Solo se reemiten certificados anulados")
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id)))
    if not progress(db, enrollment, lessons, activities)["completed"]:
        raise HTTPException(409, "El estudiante aún no cumple los requisitos")
    certificate.verification_code = secrets.token_urlsafe(24)
    certificate.status = "issued"
    certificate.issued_at = datetime.now(timezone.utc)
    certificate.revoked_at = None
    record(db, profile, "certificate_reissued", course.id)
    db.commit()
    return {"status": "issued"}


@router.get("/certificates/verify/{code}")
def verify_certificate(code: str, db: Session = Depends(get_db)):
    if len(code) != 32:
        raise HTTPException(404, "Certificado no encontrado")
    row = db.execute(select(Certificate, Enrollment, Course).join(Enrollment, Certificate.enrollment_id == Enrollment.id).join(Course, Enrollment.course_id == Course.id).where(Certificate.verification_code == code)).first()
    if row is None:
        raise HTTPException(404, "Certificado no encontrado")
    certificate, _, course = row
    return {"valid": certificate.status == "issued", "status": certificate.status, "course": course.title, "issued_at": certificate.issued_at}

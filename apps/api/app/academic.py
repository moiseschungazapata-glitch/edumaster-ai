"""Institution-scoped academic workflows. The client never supplies identity or grades."""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import AcademicEvent, Activity, Attempt, Course, Enrollment, LearningPath, Lesson, LessonProgress, PathCourse, Profile
from app.core.security import get_current_profile

router = APIRouter(tags=["academic"])
EDITORS = {"superadmin", "admin", "coordinator", "teacher"}


def record(db: Session, profile: Profile, kind: str, course_id: uuid.UUID | None = None):
    db.add(AcademicEvent(institution_id=institution(profile), actor_id=profile.id, course_id=course_id, kind=kind))


class CourseInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=5000)


class PathInput(CourseInput):
    course_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class LessonInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(min_length=1, max_length=20000)


class ActivityInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    question: str = Field(min_length=2, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0, le=5)


class AnswerInput(BaseModel):
    selected_index: int = Field(ge=0, le=5)


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
    total = len(lessons) + len(activities)
    return {"completed_lesson_ids": list(done), "passed_activity_ids": list(passed), "percent": round(100 * (len(done) + len(passed)) / total) if total else 0, "completed": bool(total and len(done) == len(lessons) and len(passed) == len(activities))}


def summary(db: Session, course: Course, profile: Profile) -> dict:
    enrolled = db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id)) if profile.role == "student" else None
    return {"id": course.id, "title": course.title, "description": course.description, "published": course.published, "teacher_id": course.teacher_id, "enrolled": bool(enrolled), "enrollment_count": db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == course.id)) if profile.role in EDITORS else None}


@router.get("/courses")
def courses(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    stmt = select(Course).where(Course.institution_id == institution(profile)).order_by(Course.title)
    if profile.role == "student":
        stmt = stmt.where(Course.published.is_(True))
    elif profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    return [summary(db, course, profile) for course in db.scalars(stmt)]


@router.post("/courses", status_code=201)
def create_course(data: CourseInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    course = Course(institution_id=institution(profile), teacher_id=profile.id, title=data.title.strip(), description=data.description.strip())
    db.add(course)
    db.flush()
    record(db, profile, "course_created", course.id)
    db.commit()
    db.refresh(course)
    return summary(db, course, profile)


@router.get("/courses/{course_id}")
def course_detail(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = db.scalar(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == profile.id)) if profile.role == "student" else None
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id == course.id).order_by(Lesson.position)))
    activities = list(db.scalars(select(Activity).where(Activity.course_id == course.id).order_by(Activity.position)))
    result = summary(db, course, profile)
    result["lessons"] = [{"id": item.id, "title": item.title, "content": item.content, "position": item.position} for item in lessons] if enrollment or profile.role in EDITORS else []
    result["activities"] = [{"id": item.id, "title": item.title, "question": item.question, "options": json.loads(item.options_json), "position": item.position, **({"correct_index": item.correct_index} if profile.role in EDITORS else {})} for item in activities] if enrollment or profile.role in EDITORS else []
    result["progress"] = progress(db, enrollment, lessons, activities) if enrollment else None
    return result


@router.patch("/courses/{course_id}")
def edit_course(course_id: uuid.UUID, data: CourseInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    course.title, course.description = data.title.strip(), data.description.strip()
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
    db.commit()
    return summary(db, course, profile)


@router.post("/courses/{course_id}/lessons", status_code=201)
def add_lesson(course_id: uuid.UUID, data: LessonInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de cambiar su contenido")
    position = (db.scalar(select(func.max(Lesson.position)).where(Lesson.course_id == course_id)) or 0) + 1
    lesson = Lesson(course_id=course_id, title=data.title.strip(), content=data.content.strip(), position=position)
    db.add(lesson)
    db.commit()
    return {"id": lesson.id, "position": position}


@router.post("/courses/{course_id}/activities", status_code=201)
def add_activity(course_id: uuid.UUID, data: ActivityInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    can_edit(profile, course)
    if course.published:
        raise HTTPException(409, "Despublica el curso antes de cambiar su evaluación")
    if data.correct_index >= len(data.options) or any(not option.strip() for option in data.options):
        raise HTTPException(422, "Opciones o respuesta correcta inválidas")
    position = (db.scalar(select(func.max(Activity.position)).where(Activity.course_id == course_id)) or 0) + 1
    activity = Activity(course_id=course_id, title=data.title.strip(), question=data.question.strip(), options_json=json.dumps([option.strip() for option in data.options]), correct_index=data.correct_index, position=position)
    db.add(activity)
    db.commit()
    return {"id": activity.id, "position": position}


@router.post("/courses/{course_id}/enroll", status_code=201)
def enroll(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    if profile.role != "student":
        raise HTTPException(403, "Solo estudiantes pueden matricularse")
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
    if data.selected_index >= len(json.loads(activity.options_json)):
        raise HTTPException(422, "Opción inválida")
    score = 100 if data.selected_index == activity.correct_index else 0
    attempt = Attempt(activity_id=activity_id, enrollment_id=enrollment.id, selected_index=data.selected_index, score=score)
    db.add(attempt)
    record(db, profile, "assessment_passed" if score >= activity.passing_score else "assessment_failed", course.id)
    db.commit()
    return {"id": attempt.id, "score": score, "passed": score >= activity.passing_score}


@router.get("/courses/{course_id}/attempts")
def my_attempts(course_id: uuid.UUID, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    course = course_or_404(db, profile, course_id)
    enrollment = enrollment_or_403(db, profile, course)
    return [{"id": a.id, "activity_id": a.activity_id, "score": a.score, "selected_index": a.selected_index} for a in db.scalars(select(Attempt).join(Activity).where(Attempt.enrollment_id == enrollment.id, Activity.course_id == course.id))]


@router.get("/paths")
def paths(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    result = []
    for path in db.scalars(select(LearningPath).where(LearningPath.institution_id == institution(profile)).order_by(LearningPath.title)):
        entries = db.execute(select(PathCourse, Course).join(Course, PathCourse.course_id == Course.id).where(PathCourse.path_id == path.id).order_by(PathCourse.position)).all()
        visible = [course for _, course in entries if (course.published or profile.role in EDITORS) and (profile.role != "teacher" or course.teacher_id == profile.id)]
        if profile.role == "student" and not visible:
            continue
        result.append({"id": path.id, "title": path.title, "description": path.description, "courses": [summary(db, course, profile) for course in visible]})
    return result


@router.post("/paths", status_code=201)
def create_path(data: PathInput, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    editor(profile)
    if len(data.course_ids) != len(set(data.course_ids)):
        raise HTTPException(422, "No repitas cursos en la ruta")
    for course_id in data.course_ids:
        course = course_or_404(db, profile, course_id)
        can_edit(profile, course)
    path = LearningPath(institution_id=institution(profile), title=data.title.strip(), description=data.description.strip())
    db.add(path)
    db.flush()
    for position, course_id in enumerate(data.course_ids, 1):
        db.add(PathCourse(path_id=path.id, course_id=course_id, position=position))
    record(db, profile, "path_created")
    db.commit()
    return {"id": path.id, "title": path.title}

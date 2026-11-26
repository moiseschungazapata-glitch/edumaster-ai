"""Institution-scoped, teacher-reviewed academic guidance.

This module never loads an offline neural checkpoint or treats a suggestion as a grade.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Activity, Attempt, Course, Enrollment, Lesson, LessonProgress, Profile, Recommendation
from app.core.security import get_current_profile
from app.audit import record as audit_record

router = APIRouter(prefix="/guidance", tags=["guidance"])
REVIEWERS = {"superadmin", "admin", "coordinator", "teacher"}
SOURCE = "academic-rules-v1"


class ActionInput(BaseModel):
    action: str


class ReviewInput(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)


class FeedbackInput(BaseModel):
    useful: bool


class TutorInput(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def _student(profile: Profile):
    if profile.role != "student" or profile.institution_id is None:
        raise HTTPException(403, "Esta vista requiere una cuenta estudiante con institución")


def _reviewer(profile: Profile):
    if profile.role not in REVIEWERS or profile.institution_id is None:
        raise HTTPException(403, "Se requiere permiso docente o de coordinación")


def _visible_review(db: Session, profile: Profile, item: Recommendation):
    _reviewer(profile)
    if item.institution_id != profile.institution_id:
        raise HTTPException(404, "Recomendación no encontrada")
    if profile.role == "teacher":
        course = db.get(Course, item.course_id)
        if course is None or course.teacher_id != profile.id:
            raise HTTPException(404, "Recomendación no encontrada")


def _owned(db: Session, profile: Profile, item_id: uuid.UUID) -> Recommendation:
    _student(profile)
    item = db.get(Recommendation, item_id)
    if item is None or item.student_id != profile.id or item.institution_id != profile.institution_id:
        raise HTTPException(404, "Recomendación no encontrada")
    return item


def _expires(item: Recommendation, now: datetime) -> bool:
    expiry = item.expires_at
    return expiry.replace(tzinfo=expiry.tzinfo or timezone.utc) <= now


def _refresh_expired(db: Session, profile: Profile, now: datetime):
    items = db.scalars(select(Recommendation).where(Recommendation.student_id == profile.id,
                                                   Recommendation.institution_id == profile.institution_id,
                                                   Recommendation.status.in_(("new", "accepted")))).all()
    changed = False
    for item in items:
        if _expires(item, now):
            item.status = "expired"
            item.updated_at = now
            changed = True
    if changed:
        db.commit()


def _serialize(db: Session, item: Recommendation) -> dict:
    course = db.get(Course, item.course_id)
    return {
        "id": item.id, "course_id": item.course_id, "course_title": course.title if course else "Curso no disponible",
        "kind": item.kind, "source": item.source, "model_version": None,
        "rationale": item.rationale, "evidence": item.evidence,
        "expected_impact": item.expected_impact, "priority": item.priority,
        "status": item.status, "review_status": item.review_status,
        "review_note": item.review_note, "feedback_useful": item.feedback_useful,
        "created_at": item.created_at, "updated_at": item.updated_at,
        "expires_at": item.expires_at,
    }


def _my_items(db: Session, profile: Profile):
    return list(db.scalars(select(Recommendation).where(
        Recommendation.student_id == profile.id,
        Recommendation.institution_id == profile.institution_id).order_by(
        Recommendation.priority.desc(), Recommendation.created_at.desc())))


@router.post("/recommendations/refresh")
def refresh(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    _student(profile)
    now = datetime.now(timezone.utc)
    _refresh_expired(db, profile, now)
    courses = list(db.scalars(select(Course).where(
        Course.institution_id == profile.institution_id, Course.published.is_(True)).order_by(Course.title).limit(50)))
    course_ids = [course.id for course in courses]
    enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.course_id.in_(course_ids), Enrollment.student_id == profile.id)))
    by_course = {entry.course_id: entry for entry in enrollments}
    enrollment_ids = [entry.id for entry in enrollments]
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id.in_(course_ids))))
    progress = list(db.scalars(select(LessonProgress).where(LessonProgress.enrollment_id.in_(enrollment_ids))))
    activities = list(db.scalars(select(Activity).where(Activity.course_id.in_(course_ids))))
    attempts = list(db.scalars(select(Attempt).where(Attempt.enrollment_id.in_(enrollment_ids))))
    done_by_enrollment: dict[uuid.UUID, set[uuid.UUID]] = {}
    for item in progress:
        done_by_enrollment.setdefault(item.enrollment_id, set()).add(item.lesson_id)
    attempts_by_enrollment: dict[uuid.UUID, list[Attempt]] = {}
    for item in attempts:
        attempts_by_enrollment.setdefault(item.enrollment_id, []).append(item)
    prior = {(item.course_id, item.kind): item for item in _my_items(db, profile)}
    generated = []
    for course in courses:
        enrollment = by_course.get(course.id)
        if enrollment is None:
            kind, priority = "start_course", 20
            reason = "Este curso publicado está disponible en tu institución."
            evidence = "Aún no estás inscrito en este curso."
            impact = "Podrás explorar sus lecciones al inscribirte."
        else:
            lesson_ids = {lesson.id for lesson in lessons if lesson.course_id == course.id}
            done = done_by_enrollment.get(enrollment.id, set())
            pending = len(lesson_ids - done)
            current_activities = [activity for activity in activities if activity.course_id == course.id]
            current_attempts = attempts_by_enrollment.get(enrollment.id, [])
            unfinished = [a for a in current_activities if not any(
                t.activity_id == a.id and t.score >= a.passing_score for t in current_attempts)]
            previously_attempted = sum(any(t.activity_id == a.id for t in current_attempts) for a in unfinished)
            if unfinished:
                kind, priority = "review_assessment", 90 if previously_attempted else 75
                reason = ("Hay una evaluación que puedes volver a practicar." if previously_attempted
                          else "Tienes una evaluación pendiente en este curso.")
                evidence = (f"{len(unfinished)} evaluación(es) pendientes de aprobar; "
                            f"{previously_attempted} con intentos previos.")
                impact = "Revisar el contenido podría ayudarte a preparar tu evaluación."
            elif pending:
                kind, priority = "continue_course", 70
                reason = "Te quedan lecciones de este curso por completar."
                evidence = f"{len(done & lesson_ids)} de {len(lesson_ids)} lecciones completadas."
                impact = "Continuar te permitirá avanzar en el curso."
            else:
                continue
        generated.append((course, kind, priority, reason, evidence, impact))
    active_keys = {(course.id, kind) for course, kind, *_ in generated[:10]}
    for key, item in prior.items():
        if key not in active_keys and item.status == "new":
            item.status, item.updated_at = "expired", now
    for course, kind, priority, reason, evidence, impact in generated[:10]:
        existing = prior.get((course.id, kind))
        if existing is None:
            db.add(Recommendation(
                institution_id=profile.institution_id, student_id=profile.id, course_id=course.id,
                kind=kind, source=SOURCE, rationale=reason, evidence=evidence,
                expected_impact=impact, priority=priority, expires_at=now + timedelta(days=30)))
        elif existing.status == "new" and existing.review_status == "pending":
            existing.evidence, existing.updated_at = evidence, now
        elif existing.status == "expired":
            existing.status, existing.review_status = "new", "pending"
            existing.reviewed_by, existing.reviewed_at, existing.review_note = None, None, ""
            existing.feedback_useful = None
            existing.evidence, existing.rationale = evidence, reason
            existing.expected_impact, existing.priority = impact, priority
            existing.created_at = existing.updated_at = now
            existing.expires_at = now + timedelta(days=30)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # Another refresh may have inserted the same recommendation.
    return {"source": SOURCE, "model_version": None, "recommendations": [_serialize(db, item) for item in _my_items(db, profile)]}


@router.get("/recommendations")
def my_recommendations(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    _student(profile)
    _refresh_expired(db, profile, datetime.now(timezone.utc))
    return {"source": SOURCE, "model_version": None,
            "recommendations": [_serialize(db, item) for item in _my_items(db, profile)]}


@router.post("/recommendations/{item_id}/action")
def act(item_id: uuid.UUID, data: ActionInput, profile: Profile = Depends(get_current_profile),
        db: Session = Depends(get_db)):
    item = _owned(db, profile, item_id)
    if data.action not in {"accept", "discard", "complete"}:
        raise HTTPException(422, "Acción inválida")
    if _expires(item, datetime.now(timezone.utc)):
        raise HTTPException(409, "La recomendación expiró")
    course = db.get(Course, item.course_id)
    if course is None or not course.published or course.institution_id != profile.institution_id:
        raise HTTPException(409, "El curso ya no está disponible")
    if item.review_status != "approved":
        raise HTTPException(409, "Esta sugerencia requiere aprobación docente")
    transition = {("new", "accept"): "accepted", ("new", "discard"): "discarded",
                  ("accepted", "complete"): "completed"}
    target = transition.get((item.status, data.action))
    if target is None:
        raise HTTPException(409, "Cambio de estado no permitido")
    item.status, item.updated_at = target, datetime.now(timezone.utc)
    audit_record(db, profile, f"recommendation_{data.action}", "recommendation", item.id)
    db.commit()
    return _serialize(db, item)


@router.post("/recommendations/{item_id}/feedback")
def feedback(item_id: uuid.UUID, data: FeedbackInput, profile: Profile = Depends(get_current_profile),
             db: Session = Depends(get_db)):
    item = _owned(db, profile, item_id)
    if item.review_status != "approved" or item.status not in {"accepted", "completed"}:
        raise HTTPException(409, "Primero acepta una recomendación aprobada")
    item.feedback_useful, item.updated_at = data.useful, datetime.now(timezone.utc)
    audit_record(db, profile, "recommendation_feedback", "recommendation", item.id)
    db.commit()
    return _serialize(db, item)


@router.get("/reviews")
def reviews(profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    _reviewer(profile)
    stmt = select(Recommendation).join(Course, Course.id == Recommendation.course_id).where(
        Recommendation.institution_id == profile.institution_id, Course.institution_id == profile.institution_id)
    if profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    items = list(db.scalars(stmt.order_by(Recommendation.created_at.desc()).limit(100)))
    return {"recommendations": [{**_serialize(db, item), "student_id": item.student_id} for item in items],
            "summary": {"total": len(items), "accepted": sum(item.status in {"accepted", "completed"} for item in items),
                        "useful": sum(item.feedback_useful is True for item in items)}}


@router.post("/reviews/{item_id}")
def review(item_id: uuid.UUID, data: ReviewInput, profile: Profile = Depends(get_current_profile),
           db: Session = Depends(get_db)):
    item = db.get(Recommendation, item_id)
    if item is None:
        raise HTTPException(404, "Recomendación no encontrada")
    _visible_review(db, profile, item)
    if data.decision not in {"approve", "reject"}:
        raise HTTPException(422, "Decisión inválida")
    course = db.get(Course, item.course_id)
    if _expires(item, datetime.now(timezone.utc)) or course is None or not course.published:
        raise HTTPException(409, "La sugerencia expiró o el curso ya no está disponible")
    if item.review_status != "pending" or item.status != "new":
        raise HTTPException(409, "Esta sugerencia ya fue revisada o cambió de estado")
    item.review_status = "approved" if data.decision == "approve" else "rejected"
    if data.decision == "reject":
        item.status = "discarded"
    item.reviewed_by = profile.id
    item.review_note = data.note.strip()
    item.reviewed_at = item.updated_at = datetime.now(timezone.utc)
    audit_record(db, profile, f"recommendation_{data.decision}", "recommendation", item.id)
    db.commit()
    return _serialize(db, item)


@router.post("/tutor")
def guided_answer(data: TutorInput, profile: Profile = Depends(get_current_profile),
                  db: Session = Depends(get_db)):
    _student(profile)
    if not any(word in data.question.lower() for word in
               ("curso", "estudi", "recomend", "progreso", "seguir", "aprender")):
        return {"answer": "Solo puedo orientar sobre tus cursos y sugerencias revisadas. Para otras preguntas, consulta a tu docente.",
                "source": SOURCE, "model_version": None, "course_id": None,
                "explanation": "Guía limitada basada en reglas; no utiliza un modelo generativo."}
    approved = next((item for item in _my_items(db, profile)
                     if item.status == "new" and item.review_status == "approved"
                     and not _expires(item, datetime.now(timezone.utc))), None)
    if approved:
        course = db.get(Course, approved.course_id)
        if course and course.published and course.institution_id == profile.institution_id:
            return {"answer": f"Puedes revisar «{course.title}». {approved.rationale} {approved.evidence}",
                    "source": SOURCE, "model_version": None, "course_id": course.id,
                    "explanation": "Respuesta basada en una sugerencia revisada por un docente. No es una nota ni una predicción."}
    return {"answer": "Todavía no hay sugerencias revisadas para tu cuenta. Consulta tus cursos o pide orientación a tu docente.",
            "source": SOURCE, "model_version": None, "course_id": None,
            "explanation": "No se generó una respuesta libre ni se utilizó un modelo predictivo."}


@router.get("/model/status")
def model_status(profile: Profile = Depends(get_current_profile)):
    benchmark = json.loads(files("app.ml").joinpath("benchmark.json").read_text(encoding="utf-8"))
    return {"name": "EduMaster Multi-Task Network", "status": benchmark["status"],
            "prediction_enabled": False, "source": benchmark["source"],
            "reason": "El candidato externo no está validado con alumnos de EduMaster",
            "benchmark": benchmark}


@router.post("/model/predict")
def predict(profile: Profile = Depends(get_current_profile)):
    raise HTTPException(503, "La inferencia no está habilitada: el candidato OULAD requiere validación local y aprobación docente")

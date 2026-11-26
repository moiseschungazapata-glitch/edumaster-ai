"""Dashboard derived from academic records, with a private resumable SSE stream."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.academic import institution
from app.core.db import engine, get_db
from app.core.models import AcademicEvent, Activity, Attempt, Course, Enrollment, Lesson, LessonProgress, Profile
from app.core.security import get_current_profile

router = APIRouter(tags=["dashboard"])
NAMES = {
    "course_created": "Curso creado", "course_published": "Curso publicado", "enrolled": "Nueva matrícula",
    "lesson_completed": "Lección completada", "assessment_passed": "Evaluación aprobada",
    "assessment_failed": "Evaluación respondida", "path_created": "Ruta creada",
}


def visible_courses(db: Session, profile: Profile) -> list[Course]:
    stmt = select(Course).where(Course.institution_id == institution(profile))
    if profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    elif profile.role == "student":
        stmt = stmt.where(Course.published.is_(True))
    return list(db.scalars(stmt))


def event_query(profile: Profile, course_ids: list, after: int = 0):
    stmt = select(AcademicEvent).where(AcademicEvent.institution_id == institution(profile), AcademicEvent.id > after)
    if profile.role == "student":
        stmt = stmt.where(AcademicEvent.actor_id == profile.id)
    elif profile.role == "teacher":
        stmt = stmt.where(AcademicEvent.course_id.in_(course_ids))
    return stmt


def event_data(event: AcademicEvent) -> dict:
    return {"id": event.id, "kind": event.kind, "title": NAMES.get(event.kind, "Actividad académica"), "course_id": event.course_id, "occurred_at": event.occurred_at.isoformat()}


@router.get("/dashboard")
def dashboard(days: int = Query(default=30, ge=1, le=90), course_id: uuid.UUID | None = None, profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if days not in (7, 30, 90):
        raise HTTPException(422, "Elige 7, 30 o 90 días")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    courses = visible_courses(db, profile)
    if course_id is not None:
        courses = [course for course in courses if course.id == course_id]
        if not courses:
            raise HTTPException(404, "Curso no encontrado")
    course_ids = [c.id for c in courses]
    # A new institution has no courses yet. Avoid a dozen empty round trips to Postgres.
    if not course_ids:
        return {
            "source": "PostgreSQL: courses, enrollments, lesson_progress, attempts, academic_events",
            "generated_at": now.isoformat(), "period_days": days,
            "metrics": {"published_courses": 0, "enrollments": 0, "students": 0, "completed_lessons": 0,
                        "passed_assessments": 0, "completion_percent": 0, "completed_enrollments": 0},
            "series": [{"start": (cutoff + timedelta(seconds=days * 86400 * index / 7)).isoformat(),
                        "enrollments": 0, "lessons": 0, "passed_assessments": 0} for index in range(7)],
            "recent_events": [],
            "cursor": db.scalar(select(AcademicEvent.id).where(AcademicEvent.institution_id == institution(profile)).order_by(AcademicEvent.id.desc()).limit(1)) or 0,
        }
    all_enrollments = list(db.scalars(select(Enrollment).where(Enrollment.course_id.in_(course_ids), *((Enrollment.student_id == profile.id,) if profile.role == "student" else ()))))
    enrollments = [entry for entry in all_enrollments if entry.created_at.replace(tzinfo=entry.created_at.tzinfo or timezone.utc) >= cutoff]
    enrollment_ids = [e.id for e in all_enrollments]
    lessons = list(db.scalars(select(Lesson).where(Lesson.course_id.in_(course_ids))))
    activities = list(db.scalars(select(Activity).where(Activity.course_id.in_(course_ids))))
    progress = list(db.scalars(select(LessonProgress).where(LessonProgress.enrollment_id.in_(enrollment_ids))))
    attempts = list(db.scalars(select(Attempt).where(Attempt.enrollment_id.in_(enrollment_ids))))
    passing = {activity.id: activity.passing_score for activity in activities}
    done = {(p.enrollment_id, p.lesson_id) for p in progress}
    passed = {(a.enrollment_id, a.activity_id) for a in attempts if a.score >= passing.get(a.activity_id, 101)}
    total_by_course = {c.id: sum(lesson.course_id == c.id for lesson in lessons) + sum(activity.course_id == c.id for activity in activities) for c in courses}
    finished = sum(bool(total_by_course[e.course_id]) and sum((e.id, lesson.id) in done for lesson in lessons if lesson.course_id == e.course_id) + sum((e.id, activity.id) in passed for activity in activities if activity.course_id == e.course_id) == total_by_course[e.course_id] for e in enrollments)
    # One query supplies recent events and the seven chart buckets.
    events = list(db.scalars(event_query(profile, course_ids).where(AcademicEvent.occurred_at >= cutoff, AcademicEvent.occurred_at < now, AcademicEvent.course_id.in_(course_ids)).order_by(AcademicEvent.id.desc())))
    buckets = []
    for index in range(7):
        start = cutoff + timedelta(seconds=days * 86400 * index / 7)
        end = cutoff + timedelta(seconds=days * 86400 * (index + 1) / 7)
        bucket_events = [event for event in events if start <= event.occurred_at.replace(tzinfo=event.occurred_at.tzinfo or timezone.utc) < end]
        buckets.append({"start": start.isoformat(), "enrollments": sum(e.kind == "enrolled" for e in bucket_events), "lessons": sum(e.kind == "lesson_completed" for e in bucket_events), "passed_assessments": sum(e.kind == "assessment_passed" for e in bucket_events)})
    return {
        "source": "PostgreSQL: courses, enrollments, lesson_progress, attempts, academic_events",
        "generated_at": now.isoformat(), "period_days": days,
        "metrics": {
            "published_courses": sum(c.published for c in courses),
            "enrollments": len(enrollments),
            "students": len({e.student_id for e in enrollments}),
            "completed_lessons": sum(p.created_at.replace(tzinfo=p.created_at.tzinfo or timezone.utc) >= cutoff for p in progress),
            "passed_assessments": sum(a.score >= passing.get(a.activity_id, 101) and a.created_at.replace(tzinfo=a.created_at.tzinfo or timezone.utc) >= cutoff for a in attempts),
            "completion_percent": round(100 * finished / len(enrollments)) if enrollments else 0,
            "completed_enrollments": finished,
        },
        "series": buckets, "recent_events": [event_data(e) for e in events[:15]],
        "cursor": db.scalar(select(AcademicEvent.id).where(AcademicEvent.institution_id == institution(profile)).order_by(AcademicEvent.id.desc()).limit(1)) or 0,
    }


@router.get("/dashboard/stream")
async def dashboard_stream(after: int = Query(default=0, ge=0), profile: Profile = Depends(get_current_profile)):
    org_id = institution(profile)
    role, user_id = profile.role, profile.id

    async def stream():
        cursor = after
        # Keep streams shorter than the Vercel function's 60-second limit.
        # The browser reconnects with its last cursor; other hosts can stream
        # for five minutes as before.
        for tick in range(15 if os.getenv("VERCEL") else 100):
            try:
                with Session(engine()) as db:
                    stmt = select(AcademicEvent).where(AcademicEvent.institution_id == org_id, AcademicEvent.id > cursor)
                    if role == "student":
                        stmt = stmt.where(AcademicEvent.actor_id == user_id)
                    elif role == "teacher":
                        stmt = stmt.join(Course, Course.id == AcademicEvent.course_id).where(Course.teacher_id == user_id)
                    events = list(db.scalars(stmt.order_by(AcademicEvent.id).limit(100)))
                for event in events:
                    cursor = event.id
                    yield f"id: {cursor}\nevent: update\ndata: {json.dumps({'id': cursor, 'kind': event.kind})}\n\n"
                if tick % 5 == 0:
                    yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                raise
            await asyncio.sleep(3)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

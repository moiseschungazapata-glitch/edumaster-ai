"""Read-only, role-scoped analytics and export from saved academic events."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import AcademicEvent, Course, Profile
from app.core.security import get_current_profile
from app.dataset import build_dataset, csv_bytes, database_stamp, manifest

router = APIRouter(prefix="/analytics", tags=["analytics"])
READERS = {"superadmin", "admin", "coordinator", "teacher", "student", "analyst", "auditor"}


def report_data(db: Session, profile: Profile, days: int, course_id: uuid.UUID | None):
    if profile.role not in READERS or profile.institution_id is None:
        raise HTTPException(403, "No tienes acceso a la analítica de una institución")
    stmt = select(Course).where(Course.institution_id == profile.institution_id)
    if profile.role == "teacher":
        stmt = stmt.where(Course.teacher_id == profile.id)
    elif profile.role == "student":
        stmt = stmt.where(Course.published.is_(True))
    courses = list(db.scalars(stmt.order_by(Course.title)))
    if course_id and all(c.id != course_id for c in courses):
        raise HTTPException(404, "Curso no encontrado")
    visible = [c for c in courses if not course_id or c.id == course_id]
    now = datetime.now(timezone.utc)
    stmt = select(AcademicEvent).where(
        AcademicEvent.institution_id == profile.institution_id,
        AcademicEvent.course_id.in_([c.id for c in visible]),
        AcademicEvent.occurred_at >= now - timedelta(days=days),
        AcademicEvent.occurred_at < now,
    )
    if profile.role == "student":
        stmt = stmt.where(AcademicEvent.actor_id == profile.id)
    events = db.scalars(stmt.order_by(AcademicEvent.id)).all() if visible else []
    records = [{"id": event.id, "kind": event.kind, "actor_id": event.actor_id,
                "course_id": event.course_id, "occurred_at": database_stamp(event.occurred_at)}
               for event in events]
    rows, quality, latest = build_dataset(records)
    metadata = manifest(rows, quality, latest, "academic_events")
    totals = {name: sum(row[name] for row in rows) for name in
              ("enrollments", "lesson_completions", "assessment_passes", "assessment_failures")}
    return {
        "source": "PostgreSQL academic_events", "schema": metadata["schema"],
        "version": metadata["version"], "generated_at": now.isoformat(),
        "as_of": metadata["as_of"], "period_days": days,
        "quality": quality, "totals": totals,
        "courses": [{"id": str(c.id), "title": c.title} for c in courses],
        "rows": rows,
    }


@router.get("/report")
def report(days: int = Query(default=30, ge=1, le=90),
           course_id: uuid.UUID | None = None,
           profile: Profile = Depends(get_current_profile),
           db: Session = Depends(get_db)):
    if days not in (7, 30, 90):
        raise HTTPException(422, "Elige 7, 30 o 90 días")
    return report_data(db, profile, days, course_id)


@router.get("/export.csv")
def export_csv(days: int = Query(default=30, ge=1, le=90),
               course_id: uuid.UUID | None = None,
               profile: Profile = Depends(get_current_profile),
               db: Session = Depends(get_db)):
    if days not in (7, 30, 90):
        raise HTTPException(422, "Elige 7, 30 o 90 días")
    data = report_data(db, profile, days, course_id)
    if data["quality"]["rejected"] or data["quality"]["duplicate_ids"]:
        raise HTTPException(409, "La exportación se detuvo por errores de calidad en los eventos")
    return Response(content=csv_bytes(data["rows"]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="edumaster-analytics.csv"',
                             "X-Dataset-Version": data["version"], "Cache-Control": "no-store"})

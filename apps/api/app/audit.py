"""Transactional audit of academic mutations, scoped by institution."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import AuditRecord, Profile
from app.core.security import get_current_profile

router = APIRouter(prefix="/audit", tags=["audit"])


def record(db: Session, profile: Profile, action: str, target_type: str,
           target_id: uuid.UUID | None = None):
    if profile.institution_id is None:
        raise HTTPException(403, "Se requiere institución")
    db.add(AuditRecord(institution_id=profile.institution_id, actor_id=profile.id,
                       action=action, target_type=target_type, target_id=target_id))


@router.get("")
def list_audit(limit: int = Query(50, ge=1, le=100),
               profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    if profile.role not in {"superadmin", "admin", "coordinator", "auditor"} or profile.institution_id is None:
        raise HTTPException(403, "No autorizado")
    rows = db.scalars(select(AuditRecord).where(AuditRecord.institution_id == profile.institution_id)
                      .order_by(AuditRecord.occurred_at.desc(), AuditRecord.id.desc()).limit(limit)).all()
    return {"events": [{"id": row.id, "actor_id": row.actor_id, "action": row.action,
                        "target_type": row.target_type, "target_id": row.target_id,
                        "occurred_at": row.occurred_at} for row in rows]}

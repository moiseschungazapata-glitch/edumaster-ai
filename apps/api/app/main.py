import json
import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import allowed_origins, database_url, supabase_url
from app.core.db import get_db
from app.core.models import Profile
from app.core.security import get_current_profile, require_roles
from app.academic import router as academic_router

logger = logging.getLogger("edumaster.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="EduMaster.ai API", version="0.1.0", docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])
app.include_router(academic_router, prefix="/api/v1")


@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"request_id": request_id, "path": request.url.path, "event": "unhandled_error"}))
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({"request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round((time.monotonic() - start) * 1000, 2)}))
    return response


@app.get("/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        supabase_url()
        database_url()
        db.execute(text("SELECT 1"))
    except (RuntimeError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=503, detail="Servicio no preparado") from exc
    return {"status": "ready"}


@app.get("/api/v1/me")
def me(profile: Profile = Depends(get_current_profile)):
    return {"id": profile.id, "email": profile.email, "role": profile.role, "institution_id": profile.institution_id}


@app.get("/api/v1/admin/ping")
def admin_ping(profile: Profile = Depends(require_roles("superadmin", "admin"))):
    return {"status": "ok", "role": profile.role}

import json
import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import allowed_origins, database_url, supabase_url
from app.core.db import get_db
from app.core.models import Profile
from app.core.security import get_current_profile, require_roles
from app.core.rate_limit import limiter
from app.academic import router as academic_router
from app.dashboard import router as dashboard_router
from app.analytics import router as analytics_router
from app.guidance import router as guidance_router
from app.audit import router as audit_router

logger = logging.getLogger("edumaster.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="EduMaster.ai API", version="0.1.0", docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])
app.include_router(academic_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(guidance_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")


@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    try:
        wait = 0
        if request.url.path.startswith("/api/v1/"):
            wait = limiter.check(f"{request.client.host if request.client else 'unknown'}:{request.method}")
        response = (JSONResponse({"detail": "Demasiadas solicitudes"}, status_code=429,
                                 headers={"Retry-After": str(wait)}) if wait else await call_next(request))
    except Exception:
        logger.exception(json.dumps({"request_id": request_id, "path": request.url.path, "event": "unhandled_error"}))
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
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

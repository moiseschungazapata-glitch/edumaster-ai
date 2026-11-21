import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import AuditRecord, Base, Institution, Profile
from app.core.rate_limit import RateLimiter
from app.core.security import get_identity
from app.main import app


def test_rate_limit_window_and_response_headers(monkeypatch):
    now = [0.0]
    limit = RateLimiter(limit=2, window=10, clock=lambda: now[0])
    assert limit.check("a") == 0
    assert limit.check("a") == 0
    assert limit.check("a") > 0
    assert limit.check("b") == 0
    now[0] = 11
    assert limit.check("a") == 0
    with TestClient(app) as client:
        response = client.get("/health/live")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-request-id"]
        monkeypatch.setattr("app.main.limiter", RateLimiter(limit=2, window=60))
        assert client.get("/api/v1/me").status_code != 429
        assert client.get("/api/v1/me").status_code != 429
        blocked = client.get("/api/v1/me")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert blocked.headers["cache-control"] == "no-store"


def test_audit_records_are_institution_scoped_and_role_gated():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    first, second, admin, outsider, student = (uuid.uuid4() for _ in range(5))
    with Session(engine) as db:
        db.add_all([Institution(id=first, name="A"), Institution(id=second, name="B")])
        db.add_all([Profile(id=admin, email="admin@a.test", role="admin", institution_id=first),
                    Profile(id=outsider, email="admin@b.test", role="admin", institution_id=second),
                    Profile(id=student, email="student@a.test", role="student", institution_id=first)])
        db.add_all([AuditRecord(institution_id=first, actor_id=admin, action="course_created", target_type="course"),
                    AuditRecord(institution_id=second, actor_id=outsider, action="course_published", target_type="course")])
        db.commit()

    current = {"id": admin}
    def session_override():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_identity] = lambda: {"sub": str(current["id"]), "role": "authenticated"}
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/audit")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert [event["action"] for event in response.json()["events"]] == ["course_created"]
            current["id"] = outsider
            assert [event["action"] for event in client.get("/api/v1/audit").json()["events"]] == ["course_published"]
            current["id"] = student
            assert client.get("/api/v1/audit").status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

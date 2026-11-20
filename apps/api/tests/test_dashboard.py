import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import Base, Institution, Profile
from app.core.security import get_identity
from app.main import app


def test_dashboard_uses_saved_events_and_isolates_institutions():
    db_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db_engine)
    institution_a, institution_b = uuid.uuid4(), uuid.uuid4()
    teacher, student, outsider = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session(db_engine) as db:
        db.add_all([Institution(id=institution_a, name="A"), Institution(id=institution_b, name="B")])
        db.add_all([Profile(id=teacher, email="teacher@a.test", role="teacher", institution_id=institution_a), Profile(id=student, email="student@a.test", role="student", institution_id=institution_a), Profile(id=outsider, email="student@b.test", role="student", institution_id=institution_b)])
        db.commit()

    current = {"id": teacher}
    def session_override():
        with Session(db_engine) as db:
            yield db

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_identity] = lambda: {"sub": str(current["id"]), "role": "authenticated"}
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/dashboard?days=8").status_code == 422
            response = client.post("/api/v1/courses", json={"title": "Estadística"})
            assert response.status_code == 201
            course_id = response.json()["id"]
            lesson_id = client.post(f"/api/v1/courses/{course_id}/lessons", json={"title": "Primera lección", "content": "Materia"}).json()["id"]
            activity_id = client.post(f"/api/v1/courses/{course_id}/activities", json={"title": "Prueba", "question": "Elige B", "options": ["A", "B"], "correct_index": 1}).json()["id"]
            client.post(f"/api/v1/courses/{course_id}/publish")
            current["id"] = student
            client.post(f"/api/v1/courses/{course_id}/enroll")
            client.post(f"/api/v1/courses/{course_id}/lessons/{lesson_id}/complete")
            client.post(f"/api/v1/courses/{course_id}/activities/{activity_id}/attempts", json={"selected_index": 1})
            own = client.get(f"/api/v1/dashboard?days=7&course_id={course_id}").json()
            assert own["metrics"]["published_courses"] == 1
            assert own["metrics"]["enrollments"] == 1
            assert own["metrics"]["completed_lessons"] == 1
            assert own["metrics"]["passed_assessments"] == 1
            assert own["metrics"]["completion_percent"] == 100
            assert len(own["series"]) == 7
            assert {e["kind"] for e in own["recent_events"]} == {"enrolled", "lesson_completed", "assessment_passed"}
            assert sum(point["lessons"] for point in own["series"]) == 1
            current["id"] = outsider
            assert client.get(f"/api/v1/dashboard?course_id={course_id}").status_code == 404
            other = client.get("/api/v1/dashboard").json()
            assert other["metrics"]["published_courses"] == 0
            assert other["recent_events"] == []
            current["id"] = teacher
            teacher_view = client.get("/api/v1/dashboard").json()
            assert teacher_view["metrics"]["completion_percent"] == 100
            assert any(e["kind"] == "enrolled" for e in teacher_view["recent_events"])
    finally:
        app.dependency_overrides.clear()
        db_engine.dispose()

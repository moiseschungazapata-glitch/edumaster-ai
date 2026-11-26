import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import Activity, Base, Course, Enrollment, Institution, Lesson, Profile
from app.core.security import get_identity
from app.main import app


def test_guidance_lifecycle_review_feedback_and_tenant_boundary():
    db_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db_engine)
    org, other = uuid.uuid4(), uuid.uuid4()
    teacher, other_teacher, student, outsider = (uuid.uuid4() for _ in range(4))
    course_id, other_course = uuid.uuid4(), uuid.uuid4()
    with Session(db_engine) as db:
        db.add_all([Institution(id=org, name="A"), Institution(id=other, name="B")])
        db.add_all([Profile(id=teacher, email="teacher@a.test", role="teacher", institution_id=org),
                    Profile(id=other_teacher, email="teacher@b.test", role="teacher", institution_id=other),
                    Profile(id=student, email="student@a.test", role="student", institution_id=org),
                    Profile(id=outsider, email="student@b.test", role="student", institution_id=other)])
        db.add_all([Course(id=course_id, institution_id=org, teacher_id=teacher, title="A", description="", published=True),
                    Course(id=other_course, institution_id=other, teacher_id=other_teacher, title="B", description="", published=True)])
        db.flush()
        db.add(Enrollment(course_id=course_id, student_id=student))
        db.add(Lesson(course_id=course_id, title="L1", content="Contenido", position=1))
        db.commit()

    current = {"id": student}
    def session_override():
        with Session(db_engine) as db:
            yield db
    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_identity] = lambda: {"sub": str(current["id"]), "role": "authenticated"}
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/guidance/model/status").json()
            assert status["status"] == "external_validation_only" and status["prediction_enabled"] is False
            assert status["benchmark"]["examples"] == 17434
            assert status["benchmark"]["metrics"]["risk_recall"] < .02
            assert client.post("/api/v1/guidance/model/predict").status_code == 503
            suggestion = client.post("/api/v1/guidance/recommendations/refresh").json()["recommendations"][0]
            assert suggestion["course_id"] == str(course_id)
            assert suggestion["source"] == "academic-rules-v1"
            assert suggestion["review_status"] == "pending"
            assert "1" in suggestion["evidence"]
            assert len(client.post("/api/v1/guidance/recommendations/refresh").json()["recommendations"]) == 1
            item_id = suggestion["id"]
            assert client.post(f"/api/v1/guidance/recommendations/{item_id}/action",
                               json={"action": "accept"}).status_code == 409
            assert client.post(f"/api/v1/guidance/recommendations/{item_id}/feedback",
                               json={"useful": True}).status_code == 409
            answer = client.post("/api/v1/guidance/tutor", json={"question": "¿Qué estudiar?"}).json()
            assert answer["model_version"] is None and answer["course_id"] is None
            current["id"] = outsider
            assert client.get("/api/v1/guidance/recommendations").json()["recommendations"] == []
            assert client.post(f"/api/v1/guidance/recommendations/{item_id}/action",
                               json={"action": "accept"}).status_code == 404
            current["id"] = other_teacher
            assert client.get("/api/v1/guidance/reviews").json()["recommendations"] == []
            assert client.post(f"/api/v1/guidance/reviews/{item_id}",
                               json={"decision": "approve"}).status_code == 404
            current["id"] = teacher
            assert len(client.get("/api/v1/guidance/reviews").json()["recommendations"]) == 1
            approved = client.post(f"/api/v1/guidance/reviews/{item_id}",
                                   json={"decision": "approve", "note": "Adelante"}).json()
            assert approved["review_status"] == "approved"
            assert client.post(f"/api/v1/guidance/reviews/{item_id}",
                               json={"decision": "reject"}).status_code == 409
            current["id"] = student
            assert client.post("/api/v1/guidance/tutor", json={"question": "¿Qué curso sigo?"}).json()["course_id"] == str(course_id)
            accepted = client.post(f"/api/v1/guidance/recommendations/{item_id}/action",
                                   json={"action": "accept"}).json()
            assert accepted["status"] == "accepted"
            assert client.post(f"/api/v1/guidance/recommendations/{item_id}/action",
                               json={"action": "discard"}).status_code == 409
            feedback = client.post(f"/api/v1/guidance/recommendations/{item_id}/feedback",
                                   json={"useful": True}).json()
            assert feedback["feedback_useful"] is True
            assert client.post(f"/api/v1/guidance/recommendations/{item_id}/action",
                               json={"action": "complete"}).json()["status"] == "completed"
            current["id"] = teacher
            assert client.get("/api/v1/guidance/reviews").json()["summary"]["useful"] == 1
            with Session(db_engine) as db:
                db.add(Activity(course_id=course_id, position=1, title="Prueba", question="¿Cuál?",
                                options_json='["A","B"]', correct_index=1))
                db.commit()
            current["id"] = student
            refreshed = client.post("/api/v1/guidance/recommendations/refresh").json()["recommendations"]
            pending = next(item for item in refreshed if item["kind"] == "review_assessment")
            assert pending["review_status"] == "pending" and "1 evaluación" in pending["evidence"]
            current["id"] = teacher
            assert client.post(f"/api/v1/guidance/reviews/{pending['id']}",
                               json={"decision": "reject", "note": "Revisar en clase"}).json()["status"] == "discarded"
            current["id"] = student
            assert client.post(f"/api/v1/guidance/recommendations/{pending['id']}/action",
                               json={"action": "accept"}).status_code == 409
    finally:
        app.dependency_overrides.clear()
        db_engine.dispose()

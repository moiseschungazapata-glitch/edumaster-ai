"""The academic flow is checked without a live Supabase account."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import Base, Certificate, Institution, Profile
from app.core.security import get_identity
from app.main import app


def test_course_enrollment_assessment_and_tenant_boundaries():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    org, other = uuid.uuid4(), uuid.uuid4()
    teacher, student, outsider, admin, cohort_student = (uuid.uuid4() for _ in range(5))
    with Session(engine) as db:
        db.add_all([Institution(id=org, name="Academia A"), Institution(id=other, name="Academia B")])
        db.add_all([Profile(id=teacher, email="docente@test.com", role="teacher", institution_id=org), Profile(id=student, email="alumno@test.com", role="student", institution_id=org), Profile(id=cohort_student, email="alumno2@test.com", role="student", institution_id=org), Profile(id=outsider, email="otro@test.com", role="student", institution_id=other), Profile(id=admin, email="admin@test.com", role="admin", institution_id=org)])
        db.commit()

    def test_db():
        with Session(engine) as db:
            yield db

    current = {"id": teacher}
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_identity] = lambda: {"sub": str(current["id"]), "role": "authenticated"}
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/courses", json={"title": "Fundamentos", "description": "Introducción"})
            assert created.status_code == 201
            course_id = created.json()["id"]
            assert client.post(f"/api/v1/courses/{course_id}/publish").status_code == 409
            lesson_id = client.post(f"/api/v1/courses/{course_id}/lessons", json={"title": "Lección 1", "content": "Contenido"}).json()["id"]
            activity_id = client.post(f"/api/v1/courses/{course_id}/activities", json={"title": "Prueba", "question": "¿Cuál?", "options": ["A", "B"], "correct_index": 1}).json()["id"]
            path = client.post("/api/v1/paths", json={"title": "Ruta inicial", "course_ids": [course_id]})
            assert path.status_code == 201
            path_id = path.json()["id"]
            assert client.post(f"/api/v1/paths/{path_id}/publish").status_code == 409
            assert client.post("/api/v1/cohorts", json={"name": "Grupo 1"}).status_code == 403
            current["id"] = admin
            cohort_id = client.post("/api/v1/cohorts", json={"name": "Grupo 1"}).json()["id"]
            assert client.post(f"/api/v1/cohorts/{cohort_id}/students", json={"student_id": str(outsider)}).status_code == 404
            assert client.post(f"/api/v1/cohorts/{cohort_id}/students", json={"student_id": str(cohort_student)}).status_code == 201
            current["id"] = teacher
            assert client.post(f"/api/v1/courses/{course_id}/publish").status_code == 200
            assert client.post(f"/api/v1/paths/{path_id}/publish").status_code == 200
            assert client.post(f"/api/v1/paths/{path_id}/assign", json={"student_id": str(outsider)}).status_code == 404
            assert client.post(f"/api/v1/paths/{path_id}/assign", json={"student_id": str(student)}).status_code == 404
            current["id"] = admin
            assert client.post(f"/api/v1/paths/{path_id}/assign", json={"student_id": str(student)}).status_code == 201
            assert client.post(f"/api/v1/paths/{path_id}/assign", json={"student_id": str(student)}).status_code == 409
            assert client.post(f"/api/v1/courses/{course_id}/enroll-cohort", json={"cohort_id": cohort_id}).json()["enrolled"] == 1
            assert client.post(f"/api/v1/courses/{course_id}/enroll-cohort", json={"cohort_id": cohort_id}).json()["already_enrolled"] == 1
            current["id"] = teacher
            assert client.post(f"/api/v1/courses/{course_id}/lessons", json={"title": "Cambio", "content": "No"}).status_code == 409

            current["id"] = outsider
            assert client.get("/api/v1/courses").json() == []
            assert client.get(f"/api/v1/courses/{course_id}").status_code == 404
            assert client.post(f"/api/v1/courses/{course_id}/enroll").status_code == 404
            assert client.get("/api/v1/certificates").json() == []

            current["id"] = student
            assert len(client.get("/api/v1/paths").json()) == 1
            assert client.get("/api/v1/paths").json()[0]["assigned_to_me"] is True
            before = client.get(f"/api/v1/courses/{course_id}").json()
            assert before["activities"] == [] and before["lessons"] == []
            assert client.post(f"/api/v1/courses/{course_id}/activities/{activity_id}/attempts", json={"selected_index": 1}).status_code == 403
            assert client.post(f"/api/v1/courses/{course_id}/enroll").status_code == 201
            assert client.post(f"/api/v1/courses/{course_id}/enroll").status_code == 409
            detail = client.get(f"/api/v1/courses/{course_id}").json()
            assert "correct_index" not in detail["activities"][0]
            assert client.post(f"/api/v1/courses/{course_id}/activities/{activity_id}/attempts", json={"selected_index": 0}).json()["score"] == 0
            assert client.post(f"/api/v1/courses/{course_id}/lessons/{lesson_id}/complete").status_code == 200
            assert client.post(f"/api/v1/courses/{course_id}/lessons/{lesson_id}/complete").status_code == 200
            assert client.get(f"/api/v1/courses/{course_id}").json()["progress"]["percent"] == 50
            assert client.post(f"/api/v1/courses/{course_id}/activities/{activity_id}/attempts", json={"selected_index": 1}).json()["passed"] is True
            assert client.get(f"/api/v1/courses/{course_id}").json()["progress"]["completed"] is True
            issued = client.get(f"/api/v1/courses/{course_id}").json()["certificate"]
            assert issued["status"] == "issued"
            assert client.post(f"/api/v1/courses/{course_id}/certificate").json()["id"] == issued["id"]
            with Session(engine) as db:
                old_code = db.get(Certificate, uuid.UUID(issued["id"])).verification_code
            assert client.get(f"/api/v1/certificates/verify/{old_code}").json()["valid"] is True
            assert client.get("/api/v1/paths").json()[0]["percent"] == 100
            pdf = client.get(f"/api/v1/certificates/{issued['id']}/pdf")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
            assert len(client.get("/api/v1/certificates").json()) == 1
            assert len(client.get(f"/api/v1/courses/{course_id}/attempts").json()) == 2
            assert client.post("/api/v1/courses", json={"title": "Prohibido"}).status_code == 403
            current["id"] = teacher
            assert client.post(f"/api/v1/certificates/{issued['id']}/revoke").status_code == 200
            assert client.get(f"/api/v1/certificates/verify/{old_code}").json()["valid"] is False
            assert client.post(f"/api/v1/certificates/{issued['id']}/reissue").status_code == 200
            assert client.get(f"/api/v1/certificates/verify/{old_code}").status_code == 404
            assert client.post(f"/api/v1/certificates/{issued['id']}/revoke").status_code == 200
            current["id"] = student
            assert client.get(f"/api/v1/certificates/{issued['id']}/pdf").status_code == 409
            assert client.post(f"/api/v1/courses/{course_id}/certificate").status_code == 409
            current["id"] = teacher
            assert client.post(f"/api/v1/courses/{course_id}/unpublish").status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

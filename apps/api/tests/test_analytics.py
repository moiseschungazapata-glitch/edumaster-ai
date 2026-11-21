import csv
import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.models import AcademicEvent, Base, Course, Institution, Profile
from app.core.security import get_identity
from app.dataset import build_dataset, csv_bytes, write_dataset
from app.main import app


def test_dataset_is_deterministic_and_rejects_bad_input(tmp_path):
    course = str(uuid.uuid4())
    actor = str(uuid.uuid4())
    good = {"id": 1, "kind": "enrolled", "actor_id": actor, "course_id": course,
            "occurred_at": "2026-01-01T10:00:00+00:00"}
    second = {**good, "id": 2, "kind": "lesson_completed"}
    rows, quality, _ = build_dataset([second, good])
    assert rows == [{"date": "2026-01-01", "course_id": course, "enrollments": 1,
                     "lesson_completions": 1, "assessment_passes": 0,
                     "assessment_failures": 0, "active_actors": 1}]
    assert actor not in csv_bytes(rows).decode()
    first = write_dataset([second, good], tmp_path / "one", "synthetic-demo")
    repeated = write_dataset([good, second], tmp_path / "two", "synthetic-demo")
    assert first == repeated
    assert (tmp_path / "one" / "daily_course_features.csv").read_bytes() == (tmp_path / "two" / "daily_course_features.csv").read_bytes()
    with pytest.raises(ValueError, match="Quality gate"):
        write_dataset([good, good], tmp_path / "invalid", "synthetic-demo")
    assert not (tmp_path / "invalid").exists()
    invalid, quality, _ = build_dataset([{**good, "occurred_at": "2026-01-01T10:00:00"}])
    assert invalid == [] and quality["rejected"] == 1


def test_analytics_respects_institution_role_and_export():
    db_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db_engine)
    org, other = uuid.uuid4(), uuid.uuid4()
    teacher, student, outsider, analyst = (uuid.uuid4() for _ in range(4))
    course, foreign = uuid.uuid4(), uuid.uuid4()
    with Session(db_engine) as db:
        db.add_all([Institution(id=org, name="A"), Institution(id=other, name="B")])
        db.add_all([
            Profile(id=teacher, email="teacher@example.com", role="teacher", institution_id=org),
            Profile(id=student, email="student@example.com", role="student", institution_id=org),
            Profile(id=outsider, email="other@example.com", role="student", institution_id=other),
            Profile(id=analyst, email="analyst@example.com", role="analyst", institution_id=org),
        ])
        db.add_all([Course(id=course, institution_id=org, teacher_id=teacher, title="Local", description="", published=True),
                    Course(id=foreign, institution_id=other, teacher_id=teacher, title="Foreign", description="", published=True)])
        db.flush()
        timestamp = datetime.now(timezone.utc)
        db.add_all([
            AcademicEvent(institution_id=org, actor_id=student, course_id=course, kind="enrolled", occurred_at=timestamp),
            AcademicEvent(institution_id=org, actor_id=student, course_id=course, kind="lesson_completed", occurred_at=timestamp),
            AcademicEvent(institution_id=other, actor_id=outsider, course_id=foreign, kind="enrolled", occurred_at=timestamp),
        ])
        db.commit()

    current = {"id": student}
    def session_override():
        with Session(db_engine) as db:
            yield db

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_identity] = lambda: {"sub": str(current["id"]), "role": "authenticated"}
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/analytics/report?days=8").status_code == 422
            assert client.get(f"/api/v1/analytics/report?course_id={foreign}").status_code == 404
            report = client.get("/api/v1/analytics/report").json()
            assert report["totals"]["enrollments"] == 1
            assert report["totals"]["lesson_completions"] == 1
            assert report["quality"]["accepted"] == 2
            assert report["rows"][0]["active_actors"] == 1
            exported = client.get("/api/v1/analytics/export.csv")
            assert exported.status_code == 200
            assert exported.headers["x-dataset-version"] == report["version"]
            assert list(csv.DictReader(io.StringIO(exported.text)))[0]["course_id"] == str(course)
            assert str(student) not in exported.text
            current["id"] = outsider
            assert client.get(f"/api/v1/analytics/export.csv?course_id={course}").status_code == 404
            assert client.get("/api/v1/analytics/report").json()["totals"]["enrollments"] == 1
            current["id"] = analyst
            assert client.get("/api/v1/analytics/report").json()["totals"]["enrollments"] == 1
            current["id"] = teacher
            assert client.get("/api/v1/analytics/report").json()["totals"]["enrollments"] == 1
    finally:
        app.dependency_overrides.clear()
        db_engine.dispose()

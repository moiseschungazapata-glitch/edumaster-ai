"""Database and PDF checks that do not require an HTTP event loop."""
import base64
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.academic import ActivityInput, AnswerInput, CohortInput, CohortStudentInput, CourseInput, GradeInput, ImportCoursesInput, LessonInput, PathInput, ResourceFileInput, UnitInput, add_activity, add_cohort_student, add_lesson, add_lesson_file, add_unit, course_student_progress, create_cohort, create_course, create_path, download_lesson_file, edit_lesson, export_courses, grade_submission, import_courses, lesson_versions, path_versions, progress, publish, publish_path, reissue_certificate, restore_lesson, submit_answer, update_path, verify_certificate
from app.certificate_pdf import render_certificate
from app.core.models import Activity, Base, Certificate, CohortMember, Course, Enrollment, Institution, Lesson, LessonProgress, Profile


def test_academic_completion_and_cohort_rules():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        institution_id = uuid.uuid4()
        teacher = Profile(id=uuid.uuid4(), institution_id=institution_id, role="teacher", email="teacher@example.org")
        student = Profile(id=uuid.uuid4(), institution_id=institution_id, role="student", email="student@example.org")
        admin = Profile(id=uuid.uuid4(), institution_id=institution_id, role="admin", email="admin@example.org")
        db.add_all([Institution(id=institution_id, name="Escuela"), teacher, student, admin])
        db.commit()
        course_id = uuid.UUID(str(create_course(CourseInput(title="Curso de prueba", code="CUR-01"), teacher, db)["id"]))
        assert import_courses(ImportCoursesInput(csv_text="code,title,description,level,tags\nCUR-02,Segundo curso,Prueba,beginner,base|curso\n"), admin, db)["created"] == 1
        assert b"CUR-02" in export_courses(admin, db).body
        unit_id = uuid.UUID(str(add_unit(course_id, UnitInput(title="Unidad 1"), teacher, db)["id"]))
        lesson_id = uuid.UUID(str(add_lesson(course_id, LessonInput(title="Leccion 1", content="Texto", unit_id=unit_id), teacher, db)["id"]))
        edit_lesson(course_id, lesson_id, LessonInput(title="Leccion 1", content="Texto corregido", unit_id=unit_id), teacher, db)
        assert len(lesson_versions(course_id, lesson_id, teacher, db)) == 2
        restore_lesson(course_id, lesson_id, 1, teacher, db)
        assert db.get(Lesson, lesson_id).content == "Texto"
        file_resource = add_lesson_file(course_id, lesson_id, ResourceFileInput(title="Lectura", artifact_base64=base64.b64encode(b"%PDF-1.4\nLectura").decode(), artifact_mime="application/pdf"), teacher, db)
        assert download_lesson_file(course_id, lesson_id, file_resource["id"], teacher, db).body.startswith(b"%PDF-1.4")
        activity_id = uuid.UUID(str(add_activity(course_id, ActivityInput(title="Quiz", question="Verdadero?", kind="true_false", correct_index=0), teacher, db)["id"]))
        short_id = uuid.UUID(str(add_activity(course_id, ActivityInput(title="Respuesta corta", question="Clave?", kind="short_answer", correct_answer="clave"), teacher, db)["id"]))
        manual_id = uuid.UUID(str(add_activity(course_id, ActivityInput(title="Trabajo practico", question="Describe tu solucion", kind="practical", rubric="Claridad de la respuesta"), teacher, db)["id"]))
        file_id = uuid.UUID(str(add_activity(course_id, ActivityInput(title="Entrega", question="Sube un PDF", kind="file_upload", rubric="Documento legible"), teacher, db)["id"]))
        cohort_id = uuid.UUID(str(create_cohort(CohortInput(name="Grupo A"), admin, db)["id"]))
        add_cohort_student(cohort_id, CohortStudentInput(student_id=student.id), admin, db)
        assert db.scalar(select(CohortMember).where(CohortMember.student_id == student.id)) is not None
        assert db.get(Course, course_id).code == "CUR-01"
        assert db.get(Lesson, lesson_id).unit_id == unit_id
        assert db.get(Activity, activity_id).options_json == '["Verdadero", "Falso"]'
        publish(course_id, teacher, db)
        path_id = uuid.UUID(str(create_path(PathInput(title="Ruta inicial", course_ids=[course_id]), teacher, db)["id"]))
        assert len(path_versions(path_id, teacher, db)) == 1
        update_path(path_id, PathInput(title="Ruta revisada", objective="Completar curso", course_ids=[course_id]), teacher, db)
        assert publish_path(path_id, teacher, db)["status"] == "published"
        assert len(path_versions(path_id, teacher, db)) == 3
        enrollment = Enrollment(course_id=course_id, student_id=student.id)
        db.add(enrollment)
        db.flush()
        db.add(LessonProgress(enrollment_id=enrollment.id, lesson_id=lesson_id))
        db.flush()
        assert submit_answer(course_id, activity_id, AnswerInput(selected_index=0), student, db)["passed"]
        assert submit_answer(course_id, short_id, AnswerInput(text_answer="incorrecta"), student, db)["score"] == 0
        assert submit_answer(course_id, short_id, AnswerInput(text_answer="CLAVE"), student, db)["passed"]
        attempt = submit_answer(course_id, manual_id, AnswerInput(text_answer="Mi ejercicio"), student, db)
        assert attempt["pending_review"] and attempt["score"] is None
        assert not progress(db, enrollment, [db.get(Lesson, lesson_id)], list(db.scalars(select(Activity).where(Activity.course_id == course_id))))["completed"]
        assert grade_submission(course_id, attempt["id"], GradeInput(score=100, feedback="Aprobado"), teacher, db)["passed"]
        upload = submit_answer(course_id, file_id, AnswerInput(artifact_base64=base64.b64encode(b"%PDF-1.4\nDocumento de prueba").decode(), artifact_mime="application/pdf"), student, db)
        assert upload["pending_review"]
        assert grade_submission(course_id, upload["id"], GradeInput(score=100), teacher, db)["passed"]
        assert progress(db, enrollment, [db.get(Lesson, lesson_id)], list(db.scalars(select(Activity).where(Activity.course_id == course_id))))["completed"]
        assert course_student_progress(course_id, teacher, db)[0]["progress"]["completed"]
        certificate = db.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
        assert certificate is not None and certificate.status == "issued"
        assert verify_certificate(certificate.verification_code, db)["valid"]
        pdf = render_certificate("Curso de prueba", student.email, certificate.verification_code, certificate.issued_at, "https://example.org/verificar")
        assert pdf.startswith(b"%PDF-1.4") and b"%%EOF" in pdf
        old_code = certificate.verification_code
        grade_submission(course_id, upload["id"], GradeInput(score=0), teacher, db)
        assert not verify_certificate(old_code, db)["valid"]
        grade_submission(course_id, upload["id"], GradeInput(score=100), teacher, db)
        assert reissue_certificate(certificate.id, teacher, db)["status"] == "issued"
        assert certificate.verification_code != old_code
    engine.dispose()

import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { apiBaseUrl, supabase, type Profile } from './auth';
import { downloadCertificate } from './CertificatesPage';

type Course = { id: string; title: string; description: string; teacher_id: string; code: string | null; level: string; tags: string[]; starts_at: string | null; ends_at: string | null; certificate_heading: string; certificate_signatory: string; published: boolean; enrolled: boolean; enrollment_count: number | null };
type Lesson = { id: string; unit_id: string | null; title: string; content: string; position: number; resources: { id: string; title: string; url: string; has_file: boolean }[] };
type Unit = { id: string; title: string; position: number };
type LessonVersion = { version: number; title: string; content: string; changed_at: string };
type Activity = { id: string; title: string; question: string; options: string[]; position: number; kind: 'multiple_choice' | 'true_false' | 'short_answer' | 'practical' | 'file_upload'; correct_index?: number; correct_answer?: string; max_attempts: number; passing_score: number; weight: number; due_at: string | null; rubric: string };
type Detail = Course & { units: Unit[]; lessons: Lesson[]; activities: Activity[]; progress: { completed_lesson_ids: string[]; passed_activity_ids: string[]; percent: number; completed: boolean } | null; certificate?: { id: string; status: string } | null };
type Attempt = { id: string; activity_id: string; score: number | null; selected_index: number; feedback: string; has_artifact: boolean };
type StudentProgress = { student_id: string; email: string; progress: { percent: number; completed: boolean }; attempts: { activity_id: string; score: number }[] };
type Submission = { id: string; activity_title: string; student_email: string; text_answer: string; score: number | null; feedback: string; has_artifact: boolean };
type BankQuestion = { id: string; course_id: string; course_title: string; title: string; kind: string };
type Path = { id: string; title: string; description: string; objective: string; duration_hours: number; prerequisite_ids: string[]; prerequisites_met: boolean; published: boolean; courses: Course[]; assigned_student_ids: string[]; assigned_to_me: boolean; target_at: string | null; percent: number };
type Student = { id: string; email: string };
type Cohort = { id: string; name: string; student_ids: string[] };

type AcademicDialog = 'create-path' | 'edit-path' | 'assign-path' | 'create-course' | 'catalog' | null;

const levelLabel: Record<string, string> = {
  beginner: 'Inicial',
  intermediate: 'Intermedio',
  advanced: 'Avanzado',
};

const activityLabel: Record<Activity['kind'], string> = {
  multiple_choice: 'Opción múltiple', true_false: 'Verdadero o falso', short_answer: 'Respuesta corta', practical: 'Actividad práctica', file_upload: 'Entrega de archivo',
};

function AcademicModal({ eyebrow, title, description, size = 'medium', onClose, children }: { eyebrow: string; title: string; description?: string; size?: 'medium' | 'large'; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  const titleId = useId();
  close.current = onClose;
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); }
      if (event.key !== 'Tab') return;
      const focusable = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') ?? []).filter(element => element.getClientRects().length > 0);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first) { event.preventDefault(); panel.current?.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.body.style.overflow = 'hidden';
    if (!panel.current?.contains(document.activeElement)) panel.current?.querySelector<HTMLElement>('button')?.focus();
    window.addEventListener('keydown', closeOnEscape);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener('keydown', closeOnEscape); if (previousFocus?.isConnected) previousFocus.focus(); };
  }, []);

  return <div className="academic-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={panel} tabIndex={-1} className={`academic-modal academic-modal--${size}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? `${titleId}-description` : undefined}>
      <header className="academic-modal-header">
        <div><span className="academic-modal-eyebrow">{eyebrow}</span><h2 id={titleId}>{title}</h2>{description && <p id={`${titleId}-description`}>{description}</p>}</div>
        <button type="button" className="academic-modal-close" aria-label="Cerrar ventana" onClick={onClose}>×</button>
      </header>
      <div className="academic-modal-body">{children}</div>
    </section>
  </div>;
}

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('La sesión venció. Inicia sesión otra vez.');
  const response = await fetch(`${apiBaseUrl}/api/v1${path}`, {
    method, signal: AbortSignal.timeout(15000), headers: { Authorization: `Bearer ${session.access_token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Error ${response.status} al guardar los datos`);
  }
  return response.json() as Promise<T>;
}

async function downloadPrivateFile(path: string, name: string) {
  const token = (await supabase?.auth.getSession())?.data.session?.access_token;
  if (!token) throw new Error('Inicia sesión nuevamente.');
  const response = await fetch(`${apiBaseUrl}/api/v1${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error(`No se pudo descargar la entrega (${response.status}).`);
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href = url; a.download = `${name}.${response.headers.get('content-type')?.includes('pdf') ? 'pdf' : response.headers.get('content-type')?.includes('png') ? 'png' : 'jpg'}`; a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function downloadSubmission(courseId: string, attemptId: string) {
  return downloadPrivateFile(`/courses/${courseId}/submissions/${attemptId}/file`, `entrega-${attemptId}`);
}

async function encodeFile(file: File): Promise<string> {
  if (file.size > 1_000_000) throw new Error('El archivo debe pesar como máximo 1 MB.');
  return new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('No se pudo leer el archivo')); reader.readAsDataURL(file); });
}

export default function AcademicPage({ section, profile }: { section: 'courses' | 'paths' | 'assessments'; profile: Profile }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [paths, setPaths] = useState<Path[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [teachers, setTeachers] = useState<Student[]>([]);
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [cohortName, setCohortName] = useState('');
  const [cohortStudents, setCohortStudents] = useState<Record<string, string>>({});
  const [selectedCohort, setSelectedCohort] = useState('');
  const [assignees, setAssignees] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [assessmentTab, setAssessmentTab] = useState<'list' | 'create' | 'reviews'>('list');
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [studentProgress, setStudentProgress] = useState<StudentProgress[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [submissionScores, setSubmissionScores] = useState<Record<string, number>>({});
  const [submissionFeedback, setSubmissionFeedback] = useState<Record<string, string>>({});
  const [bankQuestions, setBankQuestions] = useState<BankQuestion[]>([]);
  const [selectedQuestion, setSelectedQuestion] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [coursePage, setCoursePage] = useState(1);
  const [levelFilter, setLevelFilter] = useState('');
  const [answer, setAnswer] = useState<Record<string, number>>({});
  const [textAnswer, setTextAnswer] = useState<Record<string, string>>({});
  const [answerFile, setAnswerFile] = useState<Record<string, File | null>>({});
  const [courseTitle, setCourseTitle] = useState('');
  const [courseDescription, setCourseDescription] = useState('');
  const [courseCode, setCourseCode] = useState('');
  const [courseLevel, setCourseLevel] = useState('beginner');
  const [courseTags, setCourseTags] = useState('');
  const [courseStart, setCourseStart] = useState('');
  const [courseEnd, setCourseEnd] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [lessonTitle, setLessonTitle] = useState('');
  const [unitTitle, setUnitTitle] = useState('');
  const [selectedUnit, setSelectedUnit] = useState('');
  const [lessonContent, setLessonContent] = useState('');
  const [resourceTitle, setResourceTitle] = useState<Record<string, string>>({});
  const [resourceUrl, setResourceUrl] = useState<Record<string, string>>({});
  const [resourceFile, setResourceFile] = useState<Record<string, File | null>>({});
  const [lessonVersions, setLessonVersions] = useState<Record<string, LessonVersion[]>>({});
  const [activityTitle, setActivityTitle] = useState('');
  const [question, setQuestion] = useState('');
  const [options, setOptions] = useState(['', '']);
  const [correct, setCorrect] = useState(0);
  const [activityKind, setActivityKind] = useState<Activity['kind']>('multiple_choice');
  const [expectedAnswer, setExpectedAnswer] = useState('');
  const [rubric, setRubric] = useState('');
  const [activityDue, setActivityDue] = useState('');
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [passingScore, setPassingScore] = useState(100);
  const [activityWeight, setActivityWeight] = useState(1);
  const [pathTitle, setPathTitle] = useState('');
  const [pathDescription, setPathDescription] = useState('');
  const [pathObjective, setPathObjective] = useState('');
  const [pathDuration, setPathDuration] = useState(0);
  const [pathPrerequisites, setPathPrerequisites] = useState<string[]>([]);
  const [pathCohorts, setPathCohorts] = useState<Record<string, string>>({});
  const [pathTargets, setPathTargets] = useState<Record<string, string>>({});
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [pathVersions, setPathVersions] = useState<Record<string, { version: number; changed_at: string }[]>>({});
  const [pathCourses, setPathCourses] = useState<string[]>([]);
  const [dialog, setDialog] = useState<AcademicDialog>(null);
  const editor = ['superadmin', 'admin', 'coordinator', 'teacher'].includes(profile.role);

  const reload = useCallback(async (id?: string | null) => {
    if (section === 'paths') {
      const [newPaths, newCourses] = await Promise.all([
        request<Path[]>('/paths'),
        editor ? request<Course[]>('/courses') : Promise.resolve([] as Course[]),
      ]);
      setPaths(newPaths); setCourses(newCourses);
      if (editor) setStudents(await request<Student[]>('/students'));
      if (editor && profile.role !== 'teacher') setCohorts(await request<Cohort[]>('/cohorts'));
    } else {
      setCourses(await request<Course[]>('/courses'));
      if (editor) setBankQuestions(await request<BankQuestion[]>('/question-bank'));
    }
    if (editor && profile.role !== 'teacher' && section === 'courses') {
      const [newCohorts, newStudents] = await Promise.all([request<Cohort[]>('/cohorts'), request<Student[]>('/students')]);
      setCohorts(newCohorts); setStudents(newStudents);
      if (profile.role !== 'teacher') setTeachers(await request<Student[]>('/teachers'));
    }
    if (id) {
      setDetail(await request<Detail>(`/courses/${id}`));
      if (profile.role === 'student') setAttempts(await request<Attempt[]>(`/courses/${id}/attempts`).catch(() => []));
      if (editor) { setStudentProgress(await request<StudentProgress[]>(`/courses/${id}/students/progress`)); setSubmissions(await request<Submission[]>(`/courses/${id}/submissions`)); }
    }
  }, [section, editor, profile.role]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void reload().catch(e => { if (active) setError((e as Error).name === 'TimeoutError' ? 'La base de datos tardó demasiado en responder. Intenta entrar nuevamente.' : (e as Error).message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  const run = async (action: () => Promise<unknown>, message: string, id = selected) => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); await reload(id); setNotice(message); return true; }
    catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(false); }
  };
  const open = async (id: string) => {
    setSelected(id); setDetail(null); setError(''); setNotice(''); setAssessmentTab('list'); setAttempts([]); setSubmissions([]); setStudentProgress([]);
    try { setDetail(await request<Detail>(`/courses/${id}`)); if (profile.role === 'student') setAttempts(await request<Attempt[]>(`/courses/${id}/attempts`).catch(() => [])); if (editor) { setStudentProgress(await request<StudentProgress[]>(`/courses/${id}/students/progress`)); setSubmissions(await request<Submission[]>(`/courses/${id}/submissions`)); } }
    catch (e) { setError((e as Error).message); }
  };
  const submitCourse = (event: FormEvent) => { event.preventDefault(); void (async () => {
    setBusy(true); setError('');
    try { const created = await request<Course>('/courses', 'POST', { title: courseTitle, description: courseDescription, code: courseCode || null, level: courseLevel, tags: courseTags.split(',').map(s => s.trim()).filter(Boolean), starts_at: courseStart ? new Date(courseStart).toISOString() : null, ends_at: courseEnd ? new Date(courseEnd).toISOString() : null }); setCourseTitle(''); setCourseDescription(''); setCourseCode(''); setCourseTags(''); setCourseStart(''); setCourseEnd(''); setSelected(created.id); await reload(created.id); setNotice('Curso creado como borrador'); setDialog(null); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  })(); };
  const submitLesson = (event: FormEvent) => { event.preventDefault(); if (!detail) return; void run(async () => { await request(`/courses/${detail.id}/lessons`, 'POST', { title: lessonTitle, content: lessonContent, unit_id: selectedUnit || null }); setLessonTitle(''); setLessonContent(''); }, 'Lección guardada'); };
  const submitActivity = (event: FormEvent) => { event.preventDefault(); if (!detail) return; void run(async () => { await request(`/courses/${detail.id}/activities`, 'POST', { title: activityTitle, question, kind: activityKind, options: activityKind === 'multiple_choice' ? options : [], correct_index: correct, correct_answer: expectedAnswer, max_attempts: maxAttempts, passing_score: passingScore, weight: activityWeight, rubric, due_at: activityDue ? new Date(activityDue).toISOString() : null }); setActivityTitle(''); setQuestion(''); setOptions(['', '']); setCorrect(0); setExpectedAnswer(''); setRubric(''); setActivityDue(''); }, 'Evaluación guardada'); };
  const submitPath = (event: FormEvent) => { event.preventDefault(); void (async () => { const saved = await run(async () => { await request('/paths', 'POST', { title: pathTitle, description: pathDescription, objective: pathObjective, duration_hours: pathDuration, course_ids: pathCourses, prerequisite_ids: pathPrerequisites }); setPathTitle(''); setPathDescription(''); setPathObjective(''); setPathDuration(0); setPathCourses([]); setPathPrerequisites([]); }, 'Ruta guardada'); if (saved) setDialog(null); })(); };
  const submitAnswer = (courseId: string, activityId: string) => { void (async () => {
    setBusy(true); setError('');
    try { const file = answerFile[activityId]; const artifact_base64 = file ? await encodeFile(file) : ''; const result = await request<{ score: number | null; pending_review: boolean }>(`/courses/${courseId}/activities/${activityId}/attempts`, 'POST', { selected_index: answer[activityId], text_answer: textAnswer[activityId] ?? '', artifact_base64, artifact_mime: file?.type ?? '' }); await reload(courseId); setNotice(result.pending_review ? 'Entrega guardada; espera la revisión docente.' : `Resultado guardado: ${result.score}%`); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  })(); };

  const activePath = paths.find(path => path.id === editingPath) ?? null;
  const filteredCourses = courses.filter(course => (!levelFilter || course.level === levelFilter) && `${course.title} ${course.description} ${course.code ?? ''} ${course.tags.join(' ')}`.toLowerCase().includes(search.toLowerCase()));

  const evaluationList = detail && <div className="assessment-list">{detail.activities.map(activity => <article className="academic-item assessment-card" key={activity.id}><div className="assessment-card-heading"><span className="assessment-kind">{activityLabel[activity.kind]}</span>{detail.progress?.passed_activity_ids.includes(activity.id) && <span className="assessment-passed">Aprobada</span>}</div><h4>{activity.title}</h4><div className="assessment-rules"><span>Nota mínima: {activity.passing_score}%</span><span>{activity.max_attempts} intentos</span><span>Peso: {activity.weight}</span></div><p>{activity.question}</p>{activity.due_at && <p>Fecha límite: {new Date(activity.due_at).toLocaleString('es-PE')}</p>}{detail.enrolled ? <>{(activity.kind === 'short_answer' || activity.kind === 'practical') ? <label>Tu respuesta<input maxLength={500} value={textAnswer[activity.id] ?? ''} onChange={e => setTextAnswer(old => ({ ...old, [activity.id]: e.target.value }))}/></label> : activity.kind === 'file_upload' ? <label>Archivo PDF, PNG o JPG (máximo 1 MB)<input type="file" accept="application/pdf,image/png,image/jpeg" onChange={e => setAnswerFile(current => ({ ...current, [activity.id]: e.target.files?.[0] ?? null }))}/></label> : <fieldset><legend>Elige una respuesta</legend>{activity.options.map((option, index) => <label key={index}><input type="radio" name={`answer-${activity.id}`} checked={answer[activity.id] === index} onChange={() => setAnswer(old => ({ ...old, [activity.id]: index }))}/>{option}</label>)}</fieldset>}<p>Intentos: {attempts.filter(item => item.activity_id === activity.id).map(item => item.score === null ? 'en revisión' : `${item.score}%`).join(', ') || 'ninguno'} (máximo {activity.max_attempts})</p>{activity.rubric && <p>Criterios: {activity.rubric}</p>}{attempts.filter(item => item.activity_id === activity.id && item.feedback).map(item => <p key={item.id}>Devolución: {item.feedback}</p>)}<button className="outline-button" disabled={busy || (activity.due_at !== null && new Date(activity.due_at).getTime() < Date.now()) || attempts.filter(item => item.activity_id === activity.id).length >= activity.max_attempts || (activity.kind === 'short_answer' || activity.kind === 'practical' ? !textAnswer[activity.id]?.trim() : activity.kind === 'file_upload' ? !answerFile[activity.id] : answer[activity.id] === undefined)} onClick={() => submitAnswer(detail.id, activity.id)}>Enviar respuesta</button>{detail.progress?.passed_activity_ids.includes(activity.id) && <span> · Aprobada</span>}</> : <p>Respuesta correcta: {activity.kind === 'short_answer' ? activity.correct_answer : activity.kind === 'practical' || activity.kind === 'file_upload' ? 'Revisión docente' : activity.options[activity.correct_index ?? 0]}</p>}</article>)}</div>;
  const submissionList = detail && <>{editor && submissions.length > 0 && <section className="academic-item"><h3>Entregas para revisar</h3>{submissions.map(item => <form className="academic-form assessment-review-card" key={item.id} onSubmit={e => { e.preventDefault(); void run(() => request(`/courses/${detail.id}/submissions/${item.id}/grade`, 'POST', { score: submissionScores[item.id] ?? item.score ?? 0, feedback: submissionFeedback[item.id] ?? item.feedback }), 'Calificación y comentarios guardados'); }}><h4>{item.activity_title} · {item.student_email}</h4>{item.text_answer && <p>{item.text_answer}</p>}{item.has_artifact && <button type="button" className="outline-button" onClick={() => void downloadSubmission(detail.id, item.id).catch(e => setError((e as Error).message))}>Descargar entrega</button>}<label>Nota de 0 a 100<input type="number" min="0" max="100" required value={submissionScores[item.id] ?? item.score ?? 0} onChange={e => setSubmissionScores(old => ({ ...old, [item.id]: Number(e.target.value) }))}/></label><label>Devolución<input maxLength={1000} value={submissionFeedback[item.id] ?? item.feedback} onChange={e => setSubmissionFeedback(old => ({ ...old, [item.id]: e.target.value }))}/></label><button className="primary-button" disabled={busy}>Guardar revisión</button></form>)}</section>}</>;
  const activityForm = detail && (<form className="academic-form academic-modal-form assessment-create-form" onSubmit={submitActivity}><h3>Añadir evaluación</h3><label>Título<input required minLength={2} value={activityTitle} onChange={e => setActivityTitle(e.target.value)}/></label><label>Pregunta<textarea required minLength={2} value={question} onChange={e => setQuestion(e.target.value)}/></label><label>Tipo<select value={activityKind} onChange={e => { setActivityKind(e.target.value as Activity['kind']); setCorrect(0); }}><option value="multiple_choice">Opción múltiple</option><option value="true_false">Verdadero o falso</option><option value="short_answer">Respuesta corta exacta</option><option value="practical">Actividad práctica</option><option value="file_upload">Entrega de archivo</option></select></label>{activityKind === 'multiple_choice' && <>{options.map((option, index) => <label key={index}>Opción {index + 1}<input required value={option} onChange={e => setOptions(current => current.map((v, i) => i === index ? e.target.value : v))}/></label>)}<button type="button" className="outline-button" disabled={options.length >= 6} onClick={() => setOptions(old => [...old, ''])}>Añadir opción</button></>}{(activityKind === 'practical' || activityKind === 'file_upload') ? <label>Criterios de revisión<textarea required maxLength={2000} value={rubric} onChange={e => setRubric(e.target.value)}/></label> : activityKind === 'short_answer' ? <label>Respuesta correcta exacta<input required maxLength={500} value={expectedAnswer} onChange={e => setExpectedAnswer(e.target.value)}/></label> : <label>Respuesta correcta<select value={correct} onChange={e => setCorrect(Number(e.target.value))}>{(activityKind === 'true_false' ? ['Verdadero', 'Falso'] : options).map((_, i) => <option value={i} key={i}>{activityKind === 'true_false' ? (i === 0 ? 'Verdadero' : 'Falso') : `Opción ${i + 1}`}</option>)}</select></label>}<label>Intentos permitidos<input type="number" min="1" max="20" required value={maxAttempts} onChange={e => setMaxAttempts(Number(e.target.value))}/></label><label>Nota mínima para aprobar<input type="number" min="1" max="100" value={passingScore} onChange={e => setPassingScore(Number(e.target.value))}/></label><label>Peso en el progreso<input type="number" min="1" max="100" value={activityWeight} onChange={e => setActivityWeight(Number(e.target.value))}/></label><label>Fecha límite (opcional)<input type="datetime-local" value={activityDue} onChange={e => setActivityDue(e.target.value)}/></label><button className="primary-button" disabled={busy}>Guardar evaluación</button></form>);

  return <div className="academic-page">
    {error && !(section === 'assessments' && selected) && <div className="academic-message academic-error" role="alert">{error}</div>}
    {notice && !(section === 'assessments' && selected) && <div className="academic-message" role="status">{notice}</div>}
    {loading && <p role="status">Cargando información académica…</p>}
    {!loading && section === 'paths' && <>
      <section className="academic-command-bar panel">
        <div className="academic-command-copy"><span className="panel-eyebrow">GESTIÓN DE RUTAS</span><strong>{paths.length} {paths.length === 1 ? 'ruta disponible' : 'rutas disponibles'}</strong><small>{paths.filter(path => path.published).length} publicadas · {paths.reduce((total, path) => total + path.assigned_student_ids.length, 0)} asignaciones</small></div>
        {editor && <button className="primary-button" onClick={() => setDialog('create-path')}><span aria-hidden="true">＋</span> Nueva ruta</button>}
      </section>
      <div className="academic-grid academic-card-grid">{paths.map(path => <article className="panel academic-panel academic-summary-card" key={path.id}>
        <div className="academic-card-top"><span className={`academic-status ${path.published ? 'academic-status--published' : 'academic-status--draft'}`}>{path.published ? 'Publicada' : 'Borrador'}</span><span className="academic-card-count">{path.courses.length} {path.courses.length === 1 ? 'curso' : 'cursos'}</span></div>
        <h2>{path.title}</h2><p className="academic-card-description">{path.description || 'Sin descripción registrada.'}</p>
        <div className="academic-meta-row">{path.duration_hours > 0 && <span>{path.duration_hours} h estimadas</span>}<span>{path.assigned_student_ids.length} estudiantes</span>{path.prerequisite_ids.length > 0 && <span>{path.prerequisite_ids.length} prerrequisitos</span>}</div>
        {path.objective && <div className="academic-objective"><small>OBJETIVO</small><p>{path.objective}</p></div>}
        <div className="academic-course-stack">{path.courses.slice(0, 4).map((course, index) => <button type="button" key={course.id} onClick={() => void open(course.id)}><span>{index + 1}</span><strong>{course.title}</strong>{course.enrolled && <small>Inscrito</small>}</button>)}{path.courses.length > 4 && <small>+ {path.courses.length - 4} cursos más</small>}</div>
        {!path.prerequisites_met && <p className="academic-warning">Completa los prerrequisitos antes de iniciar.</p>}
        {path.assigned_to_me && <div className="academic-progress"><div><span>Tu avance</span><strong>{path.percent}%</strong></div><i><span style={{ width: `${path.percent}%` }}/></i></div>}
        {editor && <footer className="academic-card-actions">
          <button className="outline-button" onClick={() => { setEditingPath(path.id); setDialog('edit-path'); void request<{ version: number; changed_at: string }[]>(`/paths/${path.id}/versions`).then(rows => setPathVersions(old => ({ ...old, [path.id]: rows }))).catch(e => setError((e as Error).message)); }}>Editar</button>
          {path.published ? <button className="outline-button" onClick={() => { setEditingPath(path.id); setDialog('assign-path'); }}>Asignar</button> : <button className="primary-button" disabled={busy || path.courses.some(course => !course.published)} onClick={() => void run(() => request(`/paths/${path.id}/publish`, 'POST'), 'Ruta publicada')}>Publicar</button>}
        </footer>}
      </article>)}</div>
      {!paths.length && <div className="academic-empty panel"><strong>Todavía no hay rutas</strong><p>Crea la primera ruta para organizar cursos y objetivos en un itinerario.</p>{editor && <button className="primary-button" onClick={() => setDialog('create-path')}>Crear primera ruta</button>}</div>}

      {dialog === 'create-path' && <AcademicModal eyebrow="RUTAS DE APRENDIZAJE" title="Crear nueva ruta" description="Define el recorrido académico y selecciona los cursos que lo componen." size="large" onClose={() => setDialog(null)}>
        <form className="academic-form academic-modal-form" onSubmit={submitPath}><div className="academic-form-grid"><label>Nombre de la ruta<input autoFocus required minLength={2} maxLength={160} value={pathTitle} onChange={e => setPathTitle(e.target.value)} placeholder="Ej. Fundamentos de analítica"/></label><label>Duración estimada (horas)<input type="number" min="0" max="10000" value={pathDuration} onChange={e => setPathDuration(Number(e.target.value))}/></label></div><label>Descripción<textarea maxLength={5000} value={pathDescription} onChange={e => setPathDescription(e.target.value)} placeholder="Resume el alcance de la ruta"/></label><label>Objetivo<textarea maxLength={2000} value={pathObjective} onChange={e => setPathObjective(e.target.value)} placeholder="¿Qué logrará el estudiante al finalizar?"/></label><div className="academic-selector-grid"><fieldset><legend>Prerrequisitos <small>Opcional</small></legend>{courses.filter(course => course.published).length ? courses.filter(course => course.published).map(course => <label key={course.id}><input type="checkbox" checked={pathPrerequisites.includes(course.id)} onChange={e => setPathPrerequisites(current => e.target.checked ? [...current, course.id] : current.filter(id => id !== course.id))}/><span>{course.title}</span></label>) : <p>No hay cursos publicados disponibles.</p>}</fieldset><fieldset><legend>Cursos de la ruta <small>Selecciona al menos uno</small></legend>{courses.length ? courses.map(course => <label key={course.id}><input type="checkbox" checked={pathCourses.includes(course.id)} onChange={e => setPathCourses(current => e.target.checked ? [...current, course.id] : current.filter(id => id !== course.id))}/><span>{course.title}</span></label>) : <p>Crea un curso antes de diseñar una ruta.</p>}</fieldset></div><div className="academic-modal-actions"><button type="button" className="outline-button" onClick={() => setDialog(null)}>Cancelar</button><button className="primary-button" disabled={busy || !pathCourses.length}>{busy ? 'Guardando…' : 'Guardar ruta'}</button></div></form>
      </AcademicModal>}

      {dialog === 'edit-path' && activePath && <AcademicModal eyebrow="RUTAS DE APRENDIZAJE" title="Editar ruta" description="Actualiza la información general sin alterar el orden de los cursos." onClose={() => setDialog(null)}>
        <form className="academic-form academic-modal-form" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); void (async () => { const saved = await run(() => request(`/paths/${activePath.id}`, 'PATCH', { title: values.get('title'), description: values.get('description'), objective: values.get('objective'), duration_hours: Number(values.get('duration')), course_ids: activePath.courses.map(course => course.id), prerequisite_ids: activePath.prerequisite_ids }), 'Ruta actualizada'); if (saved) setDialog(null); })(); }}><label>Nombre<input autoFocus name="title" required minLength={2} defaultValue={activePath.title}/></label><label>Descripción<textarea name="description" defaultValue={activePath.description}/></label><label>Objetivo<textarea name="objective" defaultValue={activePath.objective}/></label><label>Duración estimada (horas)<input name="duration" type="number" min="0" max="10000" defaultValue={activePath.duration_hours}/></label><p className="academic-version-note">Historial: {pathVersions[activePath.id]?.length ? pathVersions[activePath.id].map(item => `v${item.version}`).join(' · ') : 'Cargando versiones…'}</p><div className="academic-modal-actions"><button type="button" className="outline-button" onClick={() => setDialog(null)}>Cancelar</button><button className="primary-button" disabled={busy}>{busy ? 'Guardando…' : 'Guardar cambios'}</button></div></form>
      </AcademicModal>}

      {dialog === 'assign-path' && activePath && <AcademicModal eyebrow="ASIGNACIÓN ACADÉMICA" title={`Asignar ${activePath.title}`} description="Selecciona un estudiante o una cohorte y define una fecha objetivo opcional." onClose={() => setDialog(null)}>
        <div className="academic-form academic-modal-form"><label>Fecha objetivo (opcional)<input type="datetime-local" value={pathTargets[activePath.id] ?? ''} onChange={e => setPathTargets(old => ({ ...old, [activePath.id]: e.target.value }))}/></label><form className="academic-assignment-row" onSubmit={event => { event.preventDefault(); void (async () => { const saved = await run(() => request(`/paths/${activePath.id}/assign`, 'POST', { student_id: assignees[activePath.id], target_at: pathTargets[activePath.id] ? new Date(pathTargets[activePath.id]).toISOString() : null }), 'Ruta asignada'); if (saved) setDialog(null); })(); }}><label>Estudiante<select aria-label={`Asignar estudiante a ${activePath.title}`} value={assignees[activePath.id] ?? ''} onChange={e => setAssignees(current => ({ ...current, [activePath.id]: e.target.value }))}><option value="">Selecciona un estudiante</option>{students.filter(student => !activePath.assigned_student_ids.includes(student.id)).map(student => <option value={student.id} key={student.id}>{student.email}</option>)}</select></label><button className="primary-button" disabled={busy || !assignees[activePath.id]}>Asignar estudiante</button></form>{profile.role !== 'teacher' && <form className="academic-assignment-row" onSubmit={event => { event.preventDefault(); void (async () => { const saved = await run(() => request(`/paths/${activePath.id}/assign-cohort`, 'POST', { cohort_id: pathCohorts[activePath.id], target_at: pathTargets[activePath.id] ? new Date(pathTargets[activePath.id]).toISOString() : null }), 'Ruta asignada a la cohorte'); if (saved) setDialog(null); })(); }}><label>Cohorte<select value={pathCohorts[activePath.id] ?? ''} onChange={e => setPathCohorts(old => ({ ...old, [activePath.id]: e.target.value }))}><option value="">Elige una cohorte</option>{cohorts.map(cohort => <option value={cohort.id} key={cohort.id}>{cohort.name}</option>)}</select></label><button className="outline-button" disabled={busy || !pathCohorts[activePath.id]}>Asignar cohorte</button></form>}<div className="academic-modal-actions"><button type="button" className="outline-button" onClick={() => setDialog(null)}>Cerrar</button></div></div>
      </AcademicModal>}
    </>}
    {!loading && (section === 'courses' || section === 'assessments') && <>
      <section className="academic-command-bar academic-command-bar--filters panel"><div className="toolbar"><div className="toolbar-search"><input aria-label="Buscar cursos reales" placeholder="Buscar por nombre, código o etiqueta…" value={search} onChange={e => { setSearch(e.target.value); setCoursePage(1); }}/></div><label>Nivel<select value={levelFilter} onChange={e => { setLevelFilter(e.target.value); setCoursePage(1); }}><option value="">Todos los niveles</option><option value="beginner">Inicial</option><option value="intermediate">Intermedio</option><option value="advanced">Avanzado</option></select></label></div>{editor && section === 'courses' && <div className="academic-command-actions"><button className="outline-button" onClick={() => setDialog('catalog')}>Catálogo CSV</button><button className="primary-button" onClick={() => setDialog('create-course')}><span aria-hidden="true">＋</span> Nuevo curso</button></div>}</section>
      <div className="academic-results-line"><span>{filteredCourses.length} {filteredCourses.length === 1 ? 'resultado' : 'resultados'}</span>{(search || levelFilter) && <button type="button" onClick={() => { setSearch(''); setLevelFilter(''); }}>Limpiar filtros</button>}</div>
      <div className="academic-grid academic-card-grid">{filteredCourses.slice(0, 12 * coursePage).map(course => <article className="panel academic-panel academic-summary-card academic-course-card" key={course.id}><div className="academic-card-top"><span className={`academic-status ${course.published ? 'academic-status--published' : 'academic-status--draft'}`}>{course.published ? 'Publicado' : 'Borrador'}</span><span className="academic-level">{levelLabel[course.level] ?? course.level}</span></div><div className="academic-course-mark" aria-hidden="true">{course.title.slice(0, 2).toUpperCase()}</div><h2>{course.title}</h2><p className="academic-card-description">{course.description || 'Sin descripción registrada.'}</p>{course.tags.length > 0 && <div className="academic-tags">{course.tags.slice(0, 3).map(tag => <span key={tag}>{tag}</span>)}</div>}<div className="academic-meta-row"><span>{course.enrolled ? 'Inscrito' : editor ? `${course.enrollment_count ?? 0} matrículas` : 'Disponible'}</span>{course.code && <span>Código {course.code}</span>}</div><footer className="academic-card-actions"><button className="outline-button" onClick={() => void open(course.id)}>{section === 'assessments' ? 'Ver evaluaciones' : 'Abrir curso'}</button></footer></article>)}</div>
      {!filteredCourses.length && <div className="academic-empty panel"><strong>No encontramos cursos</strong><p>{courses.length ? 'Prueba con otro término o limpia los filtros.' : 'Crea el primer curso para comenzar a organizar contenidos.'}</p>{editor && section === 'courses' && !courses.length && <button className="primary-button" onClick={() => setDialog('create-course')}>Crear primer curso</button>}</div>}
      {filteredCourses.length > 12 * coursePage && <button className="outline-button academic-load-more" onClick={() => setCoursePage(page => page + 1)}>Mostrar más cursos</button>}

      {dialog === 'create-course' && <AcademicModal eyebrow="CURSOS Y CONTENIDOS" title="Crear nuevo curso" description="Registra la información esencial. El curso se guardará como borrador." size="large" onClose={() => setDialog(null)}><form className="academic-form academic-modal-form" onSubmit={submitCourse}><div className="academic-form-grid"><label>Título del curso<input autoFocus required minLength={2} maxLength={160} value={courseTitle} onChange={e => setCourseTitle(e.target.value)} placeholder="Ej. Matemática aplicada"/></label><label>Código único (opcional)<input maxLength={40} value={courseCode} onChange={e => setCourseCode(e.target.value)} placeholder="MAT-101"/></label></div><label>Descripción<textarea maxLength={5000} value={courseDescription} onChange={e => setCourseDescription(e.target.value)} placeholder="Describe el propósito y alcance del curso"/></label><div className="academic-form-grid"><label>Nivel<select value={courseLevel} onChange={e => setCourseLevel(e.target.value)}><option value="beginner">Inicial</option><option value="intermediate">Intermedio</option><option value="advanced">Avanzado</option></select></label><label>Etiquetas<input value={courseTags} onChange={e => setCourseTags(e.target.value)} placeholder="matemática, fundamentos"/></label><label>Inicio (opcional)<input type="datetime-local" value={courseStart} onChange={e => setCourseStart(e.target.value)}/></label><label>Cierre (opcional)<input type="datetime-local" value={courseEnd} onChange={e => setCourseEnd(e.target.value)}/></label></div><div className="academic-modal-actions"><button type="button" className="outline-button" onClick={() => setDialog(null)}>Cancelar</button><button className="primary-button" disabled={busy}>{busy ? 'Creando…' : 'Crear borrador'}</button></div></form></AcademicModal>}

      {dialog === 'catalog' && <AcademicModal eyebrow="ADMINISTRACIÓN DE CONTENIDO" title="Importar y exportar catálogo" description="Descarga una copia del catálogo o incorpora cursos desde un archivo CSV." onClose={() => setDialog(null)}><div className="academic-catalog-options"><section><div><strong>Exportar catálogo</strong><p>Descarga todos los cursos en formato CSV para respaldo o edición externa.</p></div><button className="outline-button" onClick={() => void (async () => { setError(''); try { const token = (await supabase?.auth.getSession())?.data.session?.access_token; const response = await fetch(`${apiBaseUrl}/api/v1/courses/export.csv`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error('No se pudo exportar'); const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = 'cursos.csv'; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 60000); } catch (e) { setError((e as Error).message); } })()}>Exportar CSV</button></section>{profile.role !== 'teacher' && <form className="academic-form" onSubmit={event => { event.preventDefault(); if (!importFile) return; void (async () => { const saved = await run(async () => { if (importFile.size > 100000) throw new Error('El CSV no debe superar 100 KB.'); await request('/courses/import.csv', 'POST', { csv_text: await importFile.text() }); setImportFile(null); }, 'Cursos importados como borradores'); if (saved) setDialog(null); })(); }}><div><strong>Importar cursos</strong><p>Columnas esperadas: code, title, description, level y tags. Máximo 100 KB.</p></div><label>Archivo CSV<input type="file" accept=".csv,text/csv" onChange={e => setImportFile(e.target.files?.[0] ?? null)}/></label><button className="primary-button" disabled={busy || !importFile}>Importar cursos</button></form>}</div><div className="academic-modal-actions"><button type="button" className="outline-button" onClick={() => setDialog(null)}>Cerrar</button></div></AcademicModal>}

      {editor && profile.role !== 'teacher' && section === 'courses' && <section className="panel academic-panel academic-admin-section"><div className="academic-section-heading"><div><span className="panel-eyebrow">GESTIÓN ACADÉMICA</span><h2>Cohortes</h2></div><span>{cohorts.length} registradas</span></div><form className="academic-form academic-inline-form" onSubmit={e => { e.preventDefault(); void run(async () => { await request('/cohorts', 'POST', { name: cohortName }); setCohortName(''); }, 'Cohorte creada'); }}><label>Nombre de la cohorte<input required minLength={2} maxLength={160} value={cohortName} onChange={e => setCohortName(e.target.value)} placeholder="Ej. Ingreso 2027-1"/></label><button className="outline-button" disabled={busy}>Crear cohorte</button></form>{cohorts.map(cohort => <div className="academic-item academic-cohort-row" key={cohort.id}><div><h3>{cohort.name}</h3><p>{cohort.student_ids.length} estudiantes</p></div><label>Añadir estudiante<select aria-label={`Añadir estudiante a ${cohort.name}`} value={cohortStudents[cohort.id] ?? ''} onChange={e => setCohortStudents(current => ({ ...current, [cohort.id]: e.target.value }))}><option value="">Selecciona un estudiante</option>{students.filter(student => !cohort.student_ids.includes(student.id)).map(student => <option value={student.id} key={student.id}>{student.email}</option>)}</select></label><button className="outline-button" disabled={busy || !cohortStudents[cohort.id]} onClick={() => void run(() => request(`/cohorts/${cohort.id}/students`, 'POST', { student_id: cohortStudents[cohort.id] }), 'Estudiante añadido a la cohorte')}>Añadir</button></div>)}</section>}
    </>}
    {selected && section === 'assessments' && <AcademicModal
      eyebrow="CENTRO DE EVALUACIONES"
      title={detail?.title ?? courses.find(course => course.id === selected)?.title ?? 'Evaluaciones del curso'}
      description="Consulta las actividades, sus criterios y resultados."
      size="large"
      onClose={() => { setSelected(null); setDetail(null); }}
    >
      <div className="assessment-workspace">
        {error && <div className="academic-message academic-error" role="alert">{error}{!detail && <button type="button" className="outline-button" onClick={() => void open(selected)}>Reintentar</button>}</div>}
        {notice && <div className="academic-message" role="status">{notice}</div>}
        {!detail ? !error && <div className="assessment-loading" role="status"><span/>Cargando evaluaciones…</div> : <>
          <div className="assessment-overview">
            <div><strong>{detail.activities.length}</strong><span>Evaluaciones</span></div>
            <div><strong>{editor ? submissions.filter(item => item.score === null).length : detail.progress?.passed_activity_ids.length ?? 0}</strong><span>{editor ? 'Entregas pendientes' : 'Aprobadas'}</span></div>
            <span className={`academic-status ${detail.published ? 'academic-status--published' : 'academic-status--draft'}`}>{detail.published ? 'Curso publicado' : 'Curso en borrador'}</span>
          </div>
          <nav className="assessment-view-nav" aria-label="Vistas de evaluaciones">
            <button type="button" aria-pressed={assessmentTab === 'list'} onClick={() => setAssessmentTab('list')}>Evaluaciones</button>
            {editor && <button type="button" aria-pressed={assessmentTab === 'reviews'} onClick={() => setAssessmentTab('reviews')}>Entregas <span>{submissions.length}</span></button>}
            {editor && !detail.published && <button type="button" aria-pressed={assessmentTab === 'create'} onClick={() => setAssessmentTab('create')}>Crear evaluación</button>}
          </nav>
          {assessmentTab === 'list' && <section aria-label="Evaluaciones del curso">
            {profile.role === 'student' && !detail.enrolled ? <div className="assessment-empty"><span className="assessment-empty-icon" aria-hidden="true">✓</span><h3>Inscríbete para comenzar</h3><p>Podrás responder las evaluaciones y consultar tus resultados.</p><button className="primary-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/enroll`, 'POST'), 'Matrícula confirmada')}>Inscribirme</button></div> : detail.activities.length ? evaluationList : <div className="assessment-empty"><span className="assessment-empty-icon" aria-hidden="true">✓</span><h3>Aún no hay evaluaciones</h3><p>{editor ? detail.published ? 'Este curso todavía no tiene actividades evaluables.' : 'Crea la primera evaluación para comprobar lo aprendido.' : 'Tu docente publicará las actividades de este curso aquí.'}</p>{editor && !detail.published && <button className="primary-button" onClick={() => setAssessmentTab('create')}>Crear primera evaluación</button>}</div>}
          </section>}
          {assessmentTab === 'reviews' && editor && <section aria-label="Entregas de estudiantes">{submissions.length ? submissionList : <div className="assessment-empty"><h3>No hay entregas para revisar</h3><p>Las respuestas que requieran revisión aparecerán aquí.</p></div>}</section>}
          {assessmentTab === 'create' && editor && !detail.published && <section aria-label="Crear evaluación">{activityForm}</section>}
        </>}
        <div className="academic-modal-actions"><button className="outline-button" type="button" onClick={() => { setSelected(null); setDetail(null); }}>Cerrar</button></div>
      </div>
    </AcademicModal>}
    {selected && section !== 'assessments' && <section className="panel academic-panel academic-detail" aria-label="Detalle del curso"><button className="outline-button" onClick={() => { setSelected(null); setDetail(null); }}>Cerrar detalle</button>{!detail ? <p>Cargando curso…</p> : <>
      <h2>{detail.title}</h2><p>{detail.description}</p>
      {editor && <form className="academic-form" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); void run(() => request(`/courses/${detail.id}`, 'PATCH', { title: values.get('title'), description: values.get('description'), code: values.get('code') || null, level: values.get('level'), tags: String(values.get('tags') ?? '').split(',').map(x => x.trim()).filter(Boolean), certificate_heading: values.get('certificate_heading'), certificate_signatory: values.get('certificate_signatory') }), 'Curso actualizado'); }}><h3>Editar datos del curso</h3><label>Título<input name="title" required minLength={2} maxLength={160} defaultValue={detail.title} key={`${detail.id}-title`}/></label><label>Descripción<textarea name="description" maxLength={5000} defaultValue={detail.description} key={`${detail.id}-description`}/></label><label>Código<input name="code" maxLength={40} defaultValue={detail.code ?? ''} key={`${detail.id}-code`}/></label><label>Nivel<select name="level" defaultValue={detail.level} key={`${detail.id}-level`}><option value="beginner">Inicial</option><option value="intermediate">Intermedio</option><option value="advanced">Avanzado</option></select></label><label>Etiquetas<input name="tags" defaultValue={detail.tags.join(', ')} key={`${detail.id}-tags`}/></label><label>Título del certificado<input name="certificate_heading" required minLength={3} maxLength={120} defaultValue={detail.certificate_heading} key={`${detail.id}-cert-heading`}/></label><label>Emisor o firmante<input name="certificate_signatory" required minLength={2} maxLength={120} defaultValue={detail.certificate_signatory} key={`${detail.id}-cert-signer`}/></label><button className="outline-button" disabled={busy}>Guardar cambios</button></form>}
      {editor && profile.role !== 'teacher' && <div className="academic-item"><h3>Docente responsable</h3><label>Asignar docente<select value={detail.teacher_id} onChange={e => void run(() => request(`/courses/${detail.id}/teacher`, 'PATCH', { teacher_id: e.target.value }), 'Docente asignado')}><option value={detail.teacher_id}>Actual: {teachers.find(t => t.id === detail.teacher_id)?.email ?? 'Administrador'}</option>{teachers.filter(t => t.id !== detail.teacher_id).map(t => <option value={t.id} key={t.id}>{t.email}</option>)}</select></label></div>}
      {detail.progress && <p><strong>Progreso guardado: {detail.progress.percent}%</strong>{detail.progress.completed ? ' · Curso completado' : ''}</p>}
      {detail.enrolled && detail.progress?.completed && !detail.certificate && <button className="outline-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/certificate`, 'POST'), 'Certificado listo para descargar')}>Emitir certificado</button>}
      {detail.certificate?.status === 'issued' && <button className="primary-button" disabled={busy} onClick={() => void downloadCertificate(detail.certificate!.id).catch(e => setError((e as Error).message))}>Descargar certificado PDF</button>}
      {editor && <div className="academic-item"><h3>Seguimiento de estudiantes ({studentProgress.length})</h3>{!studentProgress.length && <p>Aún no hay matrículas en este curso.</p>}{studentProgress.map(student => <p key={student.student_id}>{student.email}: {student.progress.percent}% {student.progress.completed ? '· Finalizó' : ''} · {student.attempts.length} intentos</p>)}</div>}
      {submissionList}
      {profile.role === 'student' && !detail.enrolled && <button className="primary-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/enroll`, 'POST'), 'Matrícula confirmada')}>Inscribirme</button>}
      {editor && !detail.published && <button className="primary-button" disabled={busy || !detail.lessons.length} onClick={() => void run(() => request(`/courses/${detail.id}/publish`, 'POST'), 'Curso publicado')}>Publicar curso</button>}
      {editor && detail.published && !detail.enrollment_count && <button className="outline-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/unpublish`, 'POST'), 'Curso devuelto a borrador')}>Volver a borrador</button>}
      {editor && profile.role !== 'teacher' && section === 'courses' && detail.published && <div className="academic-item"><h3>Matricular cohorte</h3><label>Cohorte<select value={selectedCohort} onChange={e => setSelectedCohort(e.target.value)}><option value="">Selecciona una cohorte</option>{cohorts.map(cohort => <option key={cohort.id} value={cohort.id}>{cohort.name} ({cohort.student_ids.length} estudiantes)</option>)}</select></label><button className="outline-button" disabled={busy || !selectedCohort} onClick={() => void run(() => request(`/courses/${detail.id}/enroll-cohort`, 'POST', { cohort_id: selectedCohort }), 'Estudiantes de la cohorte matriculados')}>Matricular estudiantes</button></div>}
      {(detail.enrolled || editor) && <><h3>Lecciones</h3>{detail.lessons.map(lesson => <article className="academic-item" key={lesson.id}><h4>{lesson.position}. {lesson.title} {lesson.unit_id && <small>· {detail.units.find(unit => unit.id === lesson.unit_id)?.title}</small>}</h4><p className="academic-content">{lesson.content}</p>{editor && !detail.published && <form className="academic-form" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); void run(() => request(`/courses/${detail.id}/lessons/${lesson.id}`, 'PATCH', { title: values.get('title'), content: values.get('content'), unit_id: lesson.unit_id }), 'Lección actualizada'); }}><label>Editar título<input name="title" required minLength={2} defaultValue={lesson.title} key={`${lesson.id}-title`}/></label><label>Editar contenido<textarea name="content" required defaultValue={lesson.content} key={`${lesson.id}-content`}/></label><button className="outline-button" disabled={busy}>Guardar nueva versión</button></form>}{editor && <><button className="outline-button" onClick={() => void request<LessonVersion[]>(`/courses/${detail.id}/lessons/${lesson.id}/versions`).then(versions => setLessonVersions(old => ({ ...old, [lesson.id]: versions }))).catch(e => setError((e as Error).message))}>Ver versiones</button>{lessonVersions[lesson.id]?.map(version => <div key={version.version}><span>Versión {version.version}: {version.title}</span>{!detail.published && <button className="outline-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/lessons/${lesson.id}/restore/${version.version}`, 'POST'), 'Versión restaurada')}>Restaurar</button>}</div>)}</>}{lesson.resources?.map(resource => <p key={resource.id}>{resource.has_file ? <button className="academic-link" onClick={() => void downloadPrivateFile(`/courses/${detail.id}/lessons/${lesson.id}/resources/${resource.id}/file`, `recurso-${resource.id}`).catch(e => setError((e as Error).message))}>Descargar {resource.title}</button> : <a href={resource.url} target="_blank" rel="noopener noreferrer">{resource.title} ↗</a>}{editor && !detail.published && <button className="outline-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/lessons/${lesson.id}/resources/${resource.id}`, 'DELETE'), 'Recurso retirado')}>Quitar recurso</button>}</p>)}{editor && !detail.published && <form className="academic-form" onSubmit={event => { event.preventDefault(); void run(async () => { await request(`/courses/${detail.id}/lessons/${lesson.id}/resources`, 'POST', { title: resourceTitle[lesson.id], url: resourceUrl[lesson.id] }); setResourceTitle(old => ({ ...old, [lesson.id]: '' })); setResourceUrl(old => ({ ...old, [lesson.id]: '' })); }, 'Recurso añadido'); }}><label>Nombre del recurso<input required minLength={2} value={resourceTitle[lesson.id] ?? ''} onChange={e => setResourceTitle(old => ({ ...old, [lesson.id]: e.target.value }))}/></label><label>Enlace HTTPS del recurso<input required type="url" pattern="https://.*" value={resourceUrl[lesson.id] ?? ''} onChange={e => setResourceUrl(old => ({ ...old, [lesson.id]: e.target.value }))}/></label><button className="outline-button" disabled={busy}>Agregar enlace</button></form>}{editor && !detail.published && <form className="academic-form" onSubmit={event => { event.preventDefault(); void run(async () => { const file = resourceFile[lesson.id]; if (!file) throw new Error("Selecciona un archivo"); await request(`/courses/${detail.id}/lessons/${lesson.id}/files`, 'POST', { title: resourceTitle[lesson.id] || file.name, artifact_base64: await encodeFile(file), artifact_mime: file.type }); setResourceFile(old => ({ ...old, [lesson.id]: null })); }, 'Archivo del curso guardado'); }}><label>Archivo del curso (PDF, PNG o JPG, máximo 1 MB)<input type="file" accept="application/pdf,image/png,image/jpeg" onChange={e => setResourceFile(old => ({ ...old, [lesson.id]: e.target.files?.[0] ?? null }))}/></label><button className="outline-button" disabled={busy || !resourceFile[lesson.id]}>Subir archivo</button></form>}{detail.enrolled && <button className="outline-button" disabled={busy || detail.progress?.completed_lesson_ids.includes(lesson.id)} onClick={() => void run(() => request(`/courses/${detail.id}/lessons/${lesson.id}/complete`, 'POST'), 'Lección completada')}>{detail.progress?.completed_lesson_ids.includes(lesson.id) ? 'Completada' : 'Marcar como completada'}</button>}</article>)}
      <h3>Evaluaciones</h3>{evaluationList}</>}
      {editor && !detail.published && <><form className="academic-form" onSubmit={event => { event.preventDefault(); void run(async () => { await request(`/courses/${detail.id}/units`, 'POST', { title: unitTitle }); setUnitTitle(''); }, 'Unidad creada'); }}><h3>Crear unidad</h3><label>Nombre<input required minLength={2} value={unitTitle} onChange={e => setUnitTitle(e.target.value)}/></label><button className="outline-button" disabled={busy}>Guardar unidad</button></form><div className="academic-grid"><form className="academic-form" onSubmit={submitLesson}><h3>Añadir lección</h3><label>Título<input required minLength={2} value={lessonTitle} onChange={e => setLessonTitle(e.target.value)}/></label><label>Unidad<select value={selectedUnit} onChange={e => setSelectedUnit(e.target.value)}><option value="">Sin unidad</option>{detail.units.map(unit => <option value={unit.id} key={unit.id}>{unit.position}. {unit.title}</option>)}</select></label><label>Contenido<textarea required value={lessonContent} onChange={e => setLessonContent(e.target.value)}/></label><button className="primary-button" disabled={busy}>Guardar lección</button></form>{activityForm}</div><div className="academic-item"><h3>Banco de preguntas</h3><label>Copiar una evaluación<select value={selectedQuestion} onChange={e => setSelectedQuestion(e.target.value)}><option value="">Selecciona una pregunta</option>{bankQuestions.map(item => <option value={item.id} key={item.id}>{item.course_title} · {item.title}</option>)}</select></label><button className="outline-button" disabled={busy || !selectedQuestion} onClick={() => void run(() => request(`/courses/${detail.id}/activities/from-bank`, 'POST', { activity_id: selectedQuestion }), 'Evaluación copiada')}>Copiar al curso</button></div></>}
    </>}</section>}
  </div>;
}

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { supabase, type Profile } from './auth';

type Course = { id: string; title: string; description: string; published: boolean; enrolled: boolean; enrollment_count: number | null };
type Lesson = { id: string; title: string; content: string; position: number };
type Activity = { id: string; title: string; question: string; options: string[]; position: number; correct_index?: number };
type Detail = Course & { lessons: Lesson[]; activities: Activity[]; progress: { completed_lesson_ids: string[]; passed_activity_ids: string[]; percent: number; completed: boolean } | null };
type Attempt = { id: string; activity_id: string; score: number; selected_index: number };
type Path = { id: string; title: string; description: string; courses: Course[] };

const apiUrl = import.meta.env.VITE_API_URL as string | undefined;
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('La sesión venció. Inicia sesión otra vez.');
  const response = await fetch(`${apiUrl?.replace(/\/$/, '')}/api/v1${path}`, {
    method, signal: AbortSignal.timeout(15000), headers: { Authorization: `Bearer ${session.access_token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Error ${response.status} al guardar los datos`);
  }
  return response.json() as Promise<T>;
}

export default function AcademicPage({ section, profile }: { section: 'courses' | 'paths' | 'assessments'; profile: Profile }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [paths, setPaths] = useState<Path[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [answer, setAnswer] = useState<Record<string, number>>({});
  const [courseTitle, setCourseTitle] = useState('');
  const [courseDescription, setCourseDescription] = useState('');
  const [lessonTitle, setLessonTitle] = useState('');
  const [lessonContent, setLessonContent] = useState('');
  const [activityTitle, setActivityTitle] = useState('');
  const [question, setQuestion] = useState('');
  const [options, setOptions] = useState(['', '']);
  const [correct, setCorrect] = useState(0);
  const [pathTitle, setPathTitle] = useState('');
  const [pathDescription, setPathDescription] = useState('');
  const [pathCourses, setPathCourses] = useState<string[]>([]);
  const editor = ['superadmin', 'admin', 'coordinator', 'teacher'].includes(profile.role);

  const reload = useCallback(async (id?: string | null) => {
    if (section === 'paths') {
      const [newPaths, newCourses] = await Promise.all([
        request<Path[]>('/paths'),
        editor ? request<Course[]>('/courses') : Promise.resolve([] as Course[]),
      ]);
      setPaths(newPaths); setCourses(newCourses);
    } else {
      setCourses(await request<Course[]>('/courses'));
    }
    if (id) {
      setDetail(await request<Detail>(`/courses/${id}`));
      if (profile.role === 'student') setAttempts(await request<Attempt[]>(`/courses/${id}/attempts`).catch(() => []));
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
    try { await action(); await reload(id); setNotice(message); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const open = async (id: string) => {
    setSelected(id); setDetail(null); setError('');
    try { setDetail(await request<Detail>(`/courses/${id}`)); if (profile.role === 'student') setAttempts(await request<Attempt[]>(`/courses/${id}/attempts`).catch(() => [])); }
    catch (e) { setError((e as Error).message); }
  };
  const submitCourse = (event: FormEvent) => { event.preventDefault(); void (async () => {
    setBusy(true); setError('');
    try { const created = await request<Course>('/courses', 'POST', { title: courseTitle, description: courseDescription }); setCourseTitle(''); setCourseDescription(''); setSelected(created.id); await reload(created.id); setNotice('Curso creado como borrador'); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  })(); };
  const submitLesson = (event: FormEvent) => { event.preventDefault(); if (!detail) return; void run(async () => { await request(`/courses/${detail.id}/lessons`, 'POST', { title: lessonTitle, content: lessonContent }); setLessonTitle(''); setLessonContent(''); }, 'Lección guardada'); };
  const submitActivity = (event: FormEvent) => { event.preventDefault(); if (!detail) return; void run(async () => { await request(`/courses/${detail.id}/activities`, 'POST', { title: activityTitle, question, options, correct_index: correct }); setActivityTitle(''); setQuestion(''); setOptions(['', '']); setCorrect(0); }, 'Evaluación guardada'); };
  const submitPath = (event: FormEvent) => { event.preventDefault(); void run(async () => { await request('/paths', 'POST', { title: pathTitle, description: pathDescription, course_ids: pathCourses }); setPathTitle(''); setPathDescription(''); setPathCourses([]); }, 'Ruta guardada'); };
  const submitAnswer = (courseId: string, activityId: string) => { void (async () => {
    setBusy(true); setError('');
    try { const result = await request<{ score: number }>(`/courses/${courseId}/activities/${activityId}/attempts`, 'POST', { selected_index: answer[activityId] }); await reload(courseId); setNotice(`Resultado guardado: ${result.score}%`); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  })(); };

  return <div className="academic-page">
    {error && <div className="academic-message academic-error" role="alert">{error}</div>}
    {notice && <div className="academic-message" role="status">{notice}</div>}
    {loading && <p role="status">Cargando información académica…</p>}
    {!loading && section === 'paths' && <>
      <div className="academic-grid">{paths.map(path => <article className="panel academic-panel" key={path.id}><span className="panel-eyebrow">RUTA DE APRENDIZAJE</span><h2>{path.title}</h2><p>{path.description}</p><ol>{path.courses.map(course => <li key={course.id}><button className="academic-link" onClick={() => { void open(course.id); }}>{course.title}</button> {course.enrolled ? '· Inscrito' : ''}</li>)}</ol></article>)}</div>
      {!paths.length && <div className="panel academic-panel">Todavía no hay rutas disponibles en tu institución.</div>}
      {editor && <form className="panel academic-panel academic-form" onSubmit={submitPath}><h2>Crear ruta</h2><label>Nombre<input required minLength={2} maxLength={160} value={pathTitle} onChange={e => setPathTitle(e.target.value)}/></label><label>Descripción<textarea maxLength={5000} value={pathDescription} onChange={e => setPathDescription(e.target.value)}/></label><fieldset><legend>Cursos en orden</legend>{courses.map(course => <label key={course.id}><input type="checkbox" checked={pathCourses.includes(course.id)} onChange={e => setPathCourses(current => e.target.checked ? [...current, course.id] : current.filter(id => id !== course.id))}/>{course.title}</label>)}</fieldset><button className="primary-button" disabled={busy || !pathCourses.length}>Guardar ruta</button></form>}
    </>}
    {!loading && (section === 'courses' || section === 'assessments') && <>
      <div className="toolbar"><div className="toolbar-search"><input aria-label="Buscar cursos reales" placeholder="Buscar cursos…" value={search} onChange={e => setSearch(e.target.value)}/></div></div>
      <div className="academic-grid">{courses.filter(c => `${c.title} ${c.description}`.toLowerCase().includes(search.toLowerCase())).map(course => <article className="panel academic-panel" key={course.id}><span className="panel-eyebrow">{course.published ? 'PUBLICADO' : 'BORRADOR'}</span><h2>{course.title}</h2><p>{course.description}</p><p>{course.enrolled ? 'Ya estás inscrito' : editor ? `${course.enrollment_count ?? 0} matrículas` : 'Disponible para inscripción'}</p><button className="outline-button" onClick={() => void open(course.id)}>{section === 'assessments' ? 'Ver evaluaciones' : 'Abrir curso'}</button></article>)}</div>
      {!courses.length && <div className="panel academic-panel">No hay cursos disponibles todavía.</div>}
      {editor && section === 'courses' && <form className="panel academic-panel academic-form" onSubmit={submitCourse}><h2>Nuevo curso</h2><label>Título<input required minLength={2} maxLength={160} value={courseTitle} onChange={e => setCourseTitle(e.target.value)}/></label><label>Descripción<textarea maxLength={5000} value={courseDescription} onChange={e => setCourseDescription(e.target.value)}/></label><button className="primary-button" disabled={busy}>Crear borrador</button></form>}
    </>}
    {selected && <section className="panel academic-panel academic-detail" aria-label="Detalle del curso"><button className="outline-button" onClick={() => { setSelected(null); setDetail(null); }}>Cerrar detalle</button>{!detail ? <p>Cargando curso…</p> : <>
      <h2>{detail.title}</h2><p>{detail.description}</p>
      {editor && <form className="academic-form" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); void run(() => request(`/courses/${detail.id}`, 'PATCH', { title: values.get('title'), description: values.get('description') }), 'Curso actualizado'); }}><h3>Editar datos del curso</h3><label>Título<input name="title" required minLength={2} maxLength={160} defaultValue={detail.title} key={`${detail.id}-title`}/></label><label>Descripción<textarea name="description" maxLength={5000} defaultValue={detail.description} key={`${detail.id}-description`}/></label><button className="outline-button" disabled={busy}>Guardar cambios</button></form>}
      {detail.progress && <p><strong>Progreso guardado: {detail.progress.percent}%</strong>{detail.progress.completed ? ' · Curso completado' : ''}</p>}
      {profile.role === 'student' && !detail.enrolled && <button className="primary-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/enroll`, 'POST'), 'Matrícula confirmada')}>Inscribirme</button>}
      {editor && !detail.published && <button className="primary-button" disabled={busy || !detail.lessons.length} onClick={() => void run(() => request(`/courses/${detail.id}/publish`, 'POST'), 'Curso publicado')}>Publicar curso</button>}
      {editor && detail.published && !detail.enrollment_count && <button className="outline-button" disabled={busy} onClick={() => void run(() => request(`/courses/${detail.id}/unpublish`, 'POST'), 'Curso devuelto a borrador')}>Volver a borrador</button>}
      {(detail.enrolled || editor) && <><h3>Lecciones</h3>{detail.lessons.map(lesson => <article className="academic-item" key={lesson.id}><h4>{lesson.position}. {lesson.title}</h4><p className="academic-content">{lesson.content}</p>{detail.enrolled && <button className="outline-button" disabled={busy || detail.progress?.completed_lesson_ids.includes(lesson.id)} onClick={() => void run(() => request(`/courses/${detail.id}/lessons/${lesson.id}/complete`, 'POST'), 'Lección completada')}>{detail.progress?.completed_lesson_ids.includes(lesson.id) ? 'Completada' : 'Marcar como completada'}</button>}</article>)}
      <h3>Evaluaciones</h3>{detail.activities.map(activity => <article className="academic-item" key={activity.id}><h4>{activity.position}. {activity.title}</h4><p>{activity.question}</p>{detail.enrolled ? <><fieldset><legend>Elige una respuesta</legend>{activity.options.map((option, index) => <label key={index}><input type="radio" name={`answer-${activity.id}`} checked={answer[activity.id] === index} onChange={() => setAnswer(old => ({ ...old, [activity.id]: index }))}/>{option}</label>)}</fieldset><p>Intentos guardados: {attempts.filter(item => item.activity_id === activity.id).map(item => `${item.score}%`).join(", ") || "ninguno"}</p><button className="outline-button" disabled={busy || answer[activity.id] === undefined} onClick={() => submitAnswer(detail.id, activity.id)}>Enviar respuesta</button>{detail.progress?.passed_activity_ids.includes(activity.id) && <span> · Aprobada</span>}</> : <p>Respuesta correcta: {activity.options[activity.correct_index ?? 0]}</p>}</article>)}</>}
      {editor && !detail.published && <div className="academic-grid"><form className="academic-form" onSubmit={submitLesson}><h3>Añadir lección</h3><label>Título<input required minLength={2} value={lessonTitle} onChange={e => setLessonTitle(e.target.value)}/></label><label>Contenido<textarea required value={lessonContent} onChange={e => setLessonContent(e.target.value)}/></label><button className="primary-button" disabled={busy}>Guardar lección</button></form><form className="academic-form" onSubmit={submitActivity}><h3>Añadir evaluación</h3><label>Título<input required minLength={2} value={activityTitle} onChange={e => setActivityTitle(e.target.value)}/></label><label>Pregunta<textarea required minLength={2} value={question} onChange={e => setQuestion(e.target.value)}/></label>{options.map((option, index) => <label key={index}>Opción {index + 1}<input required value={option} onChange={e => setOptions(current => current.map((v, i) => i === index ? e.target.value : v))}/></label>)}<button type="button" className="outline-button" disabled={options.length >= 6} onClick={() => setOptions(old => [...old, ''])}>Añadir opción</button><label>Respuesta correcta<select value={correct} onChange={e => setCorrect(Number(e.target.value))}>{options.map((_, i) => <option value={i} key={i}>Opción {i + 1}</option>)}</select></label><button className="primary-button" disabled={busy}>Guardar evaluación</button></form></div>}
    </>}</section>}
  </div>;
}

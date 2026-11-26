import { useCallback, useEffect, useState } from 'react';
import { apiBaseUrl, supabase, type Profile } from './auth';

export type DashboardData = {
  source: string; generated_at: string; period_days: number; cursor: number;
  metrics: { published_courses: number; enrollments: number; students: number; completed_lessons: number; passed_assessments: number; completion_percent: number; completed_enrollments: number };
  series: { start: string; enrollments: number; lessons: number; passed_assessments: number }[];
  recent_events: { id: number; title: string; kind: string; course_id: string | null; occurred_at: string }[];
};
type Course = { id: string; title: string };
const apiUrl = apiBaseUrl;
const dateText = (value: string) => new Intl.DateTimeFormat('es-PE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Lima' }).format(new Date(value));

export function useDashboard(profile: Profile | null, enabled = true) {
  const [days, setDays] = useState(30);
  const [courseId, setCourseId] = useState('');
  const [data, setData] = useState<DashboardData | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const reload = useCallback(async (signal?: AbortSignal) => {
    if (!profile) return null;
    const session = (await supabase?.auth.getSession())?.data.session;
    if (!session) throw new Error('La sesión venció. Vuelve a iniciar sesión.');
    const headers = { Authorization: `Bearer ${session.access_token}` };
    const requestSignal = signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000);
    const response = await fetch(`${apiUrl}/api/v1/dashboard?days=${days}${courseId ? `&course_id=${encodeURIComponent(courseId)}` : ''}`, { headers, signal: requestSignal });
    if (!response.ok) throw new Error(`No se pudieron cargar los indicadores (${response.status}).`);
    const next = await response.json() as DashboardData;
    if (!signal?.aborted) { setData(next); setError(''); }
    return next;
  }, [profile, days, courseId]);

  useEffect(() => {
    if (!profile) { setData(null); setCourses([]); setCourseId(''); setDays(30); setError(''); return; }
    if (!enabled) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const session = (await supabase?.auth.getSession())?.data.session;
        if (!session) return;
        const response = await fetch(`${apiUrl}/api/v1/courses`, { headers: { Authorization: `Bearer ${session.access_token}` }, signal: controller.signal });
        if (response.ok) setCourses(await response.json() as Course[]);
      } catch { /* The dashboard error reports unavailable backend data. */ }
    })();
    return () => controller.abort();
  }, [profile, enabled]);

  useEffect(() => {
    if (!profile || !enabled) return;
    const controller = new AbortController();
    let cursor = 0;
    const load = async () => {
      try { const next = await reload(controller.signal); if (next) cursor = Math.max(cursor, next.cursor); }
      catch (e) { if (!controller.signal.aborted) setError((e as Error).name === 'TimeoutError' ? 'La base de datos tardó demasiado en responder. Intenta actualizar.' : (e as Error).message); }
    };
    const interval = window.setInterval(() => void load(), 60000);
    const stream = async () => {
      while (!controller.signal.aborted) {
        try {
          const session = (await supabase?.auth.getSession())?.data.session;
          if (!session) throw new Error('Sesión vencida');
          const response = await fetch(`${apiUrl}/api/v1/dashboard/stream?after=${cursor}`, { headers: { Authorization: `Bearer ${session.access_token}`, Accept: 'text/event-stream' }, signal: controller.signal });
          if (!response.ok || !response.body) throw new Error('Canal de eventos no disponible');
          setConnected(true);
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
            let boundary = buffer.indexOf('\n\n');
            while (boundary >= 0) {
              const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
              const id = frame.match(/^id:\s*(\d+)/m);
              if (id && Number(id[1]) > cursor) { cursor = Number(id[1]); void load(); }
              boundary = buffer.indexOf('\n\n');
            }
          }
        } catch { /* Reconnect with the last event cursor; periodic refresh remains active. */ }
        setConnected(false);
        if (!controller.signal.aborted) await new Promise<void>(resolve => { const timer = window.setTimeout(resolve, 5000); controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true }); });
      }
    };
    void (async () => { await load(); if (!controller.signal.aborted) await stream(); })();
    return () => { controller.abort(); clearInterval(interval); setConnected(false); };
  }, [profile, enabled, reload]);
  return { data, courses, days, setDays, courseId, setCourseId, error, connected, reload };
}

export type DashboardState = ReturnType<typeof useDashboard>;

export function LiveDashboard({ state, onNavigate }: { state: DashboardState; onNavigate: (section: string) => void }) {
  const { data, courses, days, setDays, courseId, setCourseId, error, connected, reload } = state;
  const m = data?.metrics;
  const max = Math.max(1, ...(data?.series.map(item => item.enrollments + item.lessons + item.passed_assessments) ?? []));
  return <div className="live-dashboard">
    <div className="live-toolbar panel"><div><span className="panel-eyebrow">DATOS ACADÉMICOS</span><h2>Actividad y progreso</h2><small>{connected ? '● Actualización en vivo' : '○ Actualización cada minuto'}</small></div><div className="live-filters"><label>Periodo<select value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>7 días</option><option value={30}>30 días</option><option value={90}>90 días</option></select></label><label>Curso<select value={courseId} onChange={e => setCourseId(e.target.value)}><option value="">Todos los cursos</option>{courses.map(course => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label><button className="outline-button" onClick={() => void reload()}>Actualizar</button></div></div>
    {error && <div className="academic-message academic-error" role="alert">{error}</div>}
    {!data && !error && <div role="status" className="panel academic-panel">Cargando indicadores…</div>}
    {data && <>
      <div className="live-kpis">{[
        ['Cursos publicados', m?.published_courses], ['Matrículas del periodo', m?.enrollments], ['Estudiantes matriculados', m?.students],
        ['Lecciones completadas', m?.completed_lessons], ['Evaluaciones aprobadas', m?.passed_assessments], ['Matrículas finalizadas', m?.completed_enrollments],
      ].map(([label, value]) => <article className="panel live-kpi" key={String(label)}><span>{label}</span><strong>{value}</strong><small>PostgreSQL · {dateText(data.generated_at)}</small></article>)}</div>
      <div className="live-main"><section className="panel academic-panel"><span className="panel-eyebrow">EVENTOS POR PERIODO</span><h2>Tendencia académica</h2><div className="live-legend"><span>■ Matrículas</span><span>■ Lecciones</span><span>■ Evaluaciones aprobadas</span></div><div className="live-bars" role="img" aria-label="Actividad académica durante el periodo">{data.series.map((point, index) => <div className="live-bar-group" key={point.start} title={`Tramo ${index + 1}: ${point.enrollments} matrículas, ${point.lessons} lecciones y ${point.passed_assessments} evaluaciones aprobadas`}><div className="live-bar blue" style={{ height: `${100 * point.enrollments / max}%` }}/><div className="live-bar teal" style={{ height: `${100 * point.lessons / max}%` }}/><div className="live-bar violet" style={{ height: `${100 * point.passed_assessments / max}%` }}/><small>{new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',timeZone:'America/Lima'}).format(new Date(point.start))}</small></div>)}</div></section>
      <section className="panel academic-panel"><span className="panel-eyebrow">FINALIZACIÓN</span><h2>{m?.completion_percent}% de matrículas finalizadas</h2><div className="progress-track"><span style={{ width: `${m?.completion_percent ?? 0}%` }}/></div><p>Una matrícula se completa al terminar todas las lecciones y aprobar todas las actividades. Se calcula sobre las matrículas creadas en el periodo.</p><button className="text-link" onClick={() => onNavigate('courses')}>Ver cursos →</button></section></div>
      <section className="panel academic-panel"><div className="live-section-head"><div><span className="panel-eyebrow">ÚLTIMOS EVENTOS</span><h2>Actividad reciente</h2></div><button className="text-link" onClick={() => onNavigate('activity')}>Ver actividad →</button></div>{data.recent_events.length ? <ul className="live-events">{data.recent_events.slice(0, 6).map(event => <li key={event.id}><span>{event.title}</span><time>{dateText(event.occurred_at)}</time></li>)}</ul> : <p>No hay actividad registrada en este periodo.</p>}</section>
      <p className="live-source">Fuente: {data.source}. Actualizado: {dateText(data.generated_at)}. Cursos publicados: total actual; matrículas y estudiantes: altas del periodo; lecciones y evaluaciones: acciones del periodo. Los datos anteriores a la migración de eventos no tienen historial retroactivo.</p>
    </>}
  </div>;
}

export function LiveActivity({ state }: { state: DashboardState }) {
  return <section className="panel academic-panel"><h2>Actividad académica</h2>{state.error && <p role="alert">{state.error}</p>}{state.data?.recent_events.length ? <ul className="live-events">{state.data.recent_events.map(event => <li key={event.id}><span>{event.title}</span><time>{dateText(event.occurred_at)}</time></li>)}</ul> : <p>Sin eventos en los últimos {state.days} días.</p>}</section>;
}

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

function AcademicTrendChart({ series }: { series: DashboardData['series'] }) {
  const lines = [
    { key: 'enrollments', label: 'Matrículas', color: 'blue' },
    { key: 'lessons', label: 'Lecciones', color: 'teal' },
    { key: 'passed_assessments', label: 'Evaluaciones aprobadas', color: 'violet' },
  ] as const;
  const maximum = Math.max(1, ...series.flatMap(point => lines.map(line => point[line.key])));
  const left = 42;
  const right = 738;
  const top = 22;
  const bottom = 185;
  const x = (index: number) => series.length === 1 ? (left + right) / 2 : left + (right - left) * index / Math.max(1, series.length - 1);
  const y = (value: number) => bottom - (bottom - top) * value / maximum;
  const date = (value: string) => new Intl.DateTimeFormat('es-PE', { day: 'numeric', month: 'short', timeZone: 'America/Lima' }).format(new Date(value));
  const path = (key: typeof lines[number]['key']) => series.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point[key])}`).join(' ');
  const hasActivity = series.some(point => lines.some(line => point[line.key] > 0));
  const ticks = maximum === 1 ? [0, 1] : [0, Math.ceil(maximum / 2), maximum];

  return <>
    <div className="live-legend" aria-label="Series del gráfico">{lines.map(line => <span className={`live-legend-${line.color}`} key={line.key}><i aria-hidden="true" />{line.label}<strong>{series.reduce((total, point) => total + point[line.key], 0)}</strong></span>)}</div>
    <div className="live-line-scroll">
      <svg className="live-line-chart" viewBox="0 0 760 235" role="img" aria-label={`Tendencia académica: ${series.length} tramos. ${lines.map(line => `${line.label}: ${series.reduce((total, point) => total + point[line.key], 0)}`).join('; ')}`}>
        <defs><linearGradient id="live-trend-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#47afff" stopOpacity=".18" /><stop offset="100%" stopColor="#47afff" stopOpacity="0" /></linearGradient></defs>
        {ticks.map(tick => <g key={tick} className={`live-line-grid${tick === 0 ? ' live-line-baseline' : ''}`}><line x1={left} x2={right} y1={y(tick)} y2={y(tick)} /><text x={left - 11} y={y(tick) + 4} textAnchor="end">{tick}</text></g>)}
        {hasActivity && series.length > 1 && <path className="live-line-area" d={`${path('enrollments')} L ${x(series.length - 1)} ${bottom} L ${x(0)} ${bottom} Z`} />}
        {hasActivity && lines.map((line, lineIndex) => <path key={line.key} className={`live-line live-line-${line.color}`} d={path(line.key)} pathLength={1} style={{ animationDelay: `${lineIndex * 150}ms` }} />)}
        {series.map((point, index) => <g className="live-line-point" key={point.start} tabIndex={0} aria-label={`${date(point.start)}: ${point.enrollments} matrículas, ${point.lessons} lecciones, ${point.passed_assessments} evaluaciones aprobadas`}>
          <title>{`${date(point.start)} · ${point.enrollments} matrículas · ${point.lessons} lecciones · ${point.passed_assessments} evaluaciones aprobadas`}</title>
          <line className="live-line-guide" x1={x(index)} x2={x(index)} y1={top} y2={bottom} />
          {hasActivity && lines.map((line, lineIndex) => <circle key={line.key} className={`live-line-dot live-line-dot-${line.color}`} cx={x(index) + (lineIndex - 1) * 5} cy={y(point[line.key])} r="4" style={{ animationDelay: `${450 + index * 65 + lineIndex * 100}ms` }} />)}
          <rect className="live-line-hit" x={x(index) - 18} y={top} width="36" height={bottom - top + 12} />
          <text className="live-line-date" x={x(index)} y="218" textAnchor="middle">{date(point.start)}</text>
        </g>)}
        {!hasActivity && <text className="live-line-empty" x="390" y="104" textAnchor="middle">Sin actividad en este periodo</text>}
      </svg>
    </div>
  </>;
}

export function LiveDashboard({ state, onNavigate }: { state: DashboardState; onNavigate: (section: string) => void }) {
  const { data, courses, days, setDays, courseId, setCourseId, error, connected, reload } = state;
  const m = data?.metrics;
  return <div className="live-dashboard">
    <div className="live-toolbar panel"><div><span className="panel-eyebrow">DATOS ACADÉMICOS</span><h2>Actividad y progreso</h2><small>{connected ? '● Actualización en vivo' : '○ Actualización cada minuto'}</small></div><div className="live-filters"><label>Periodo<select value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>7 días</option><option value={30}>30 días</option><option value={90}>90 días</option></select></label><label>Curso<select value={courseId} onChange={e => setCourseId(e.target.value)}><option value="">Todos los cursos</option>{courses.map(course => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label><button className="outline-button" onClick={() => void reload()}>Actualizar</button></div></div>
    {error && <div className="academic-message academic-error" role="alert">{error}</div>}
    {!data && !error && <div role="status" className="panel academic-panel">Cargando indicadores…</div>}
    {data && <>
      <div className="live-kpis">{[
        ['Cursos publicados', m?.published_courses], ['Matrículas del periodo', m?.enrollments], ['Estudiantes matriculados', m?.students],
        ['Lecciones completadas', m?.completed_lessons], ['Evaluaciones aprobadas', m?.passed_assessments], ['Matrículas finalizadas', m?.completed_enrollments],
      ].map(([label, value]) => <article className="panel live-kpi" key={String(label)}><span>{label}</span><strong>{value}</strong><small>PostgreSQL · {dateText(data.generated_at)}</small></article>)}</div>
      <div className="live-main"><section className="panel academic-panel"><span className="panel-eyebrow">EVENTOS POR PERIODO</span><h2>Tendencia académica</h2><AcademicTrendChart key={`${days}-${courseId}`} series={data.series} /></section>
      <section className="panel academic-panel"><span className="panel-eyebrow">FINALIZACIÓN</span><h2>{m?.completion_percent}% de matrículas finalizadas</h2><div className="progress-track"><span style={{ width: `${m?.completion_percent ?? 0}%` }}/></div><p>Una matrícula se completa al terminar todas las lecciones y aprobar todas las actividades. Se calcula sobre las matrículas creadas en el periodo.</p><button className="text-link" onClick={() => onNavigate('courses')}>Ver cursos →</button></section></div>
      <section className="panel academic-panel"><div className="live-section-head"><div><span className="panel-eyebrow">ÚLTIMOS EVENTOS</span><h2>Actividad reciente</h2></div><button className="text-link" onClick={() => onNavigate('activity')}>Ver actividad →</button></div>{data.recent_events.length ? <ul className="live-events">{data.recent_events.slice(0, 6).map(event => <li key={event.id}><span>{event.title}</span><time>{dateText(event.occurred_at)}</time></li>)}</ul> : <p>No hay actividad registrada en este periodo.</p>}</section>
      <p className="live-source">Fuente: {data.source}. Actualizado: {dateText(data.generated_at)}. Cursos publicados: total actual; matrículas y estudiantes: altas del periodo; lecciones y evaluaciones: acciones del periodo. Los datos anteriores a la migración de eventos no tienen historial retroactivo.</p>
    </>}
  </div>;
}

export function LiveActivity({ state }: { state: DashboardState }) {
  return <section className="panel academic-panel"><h2>Actividad académica</h2>{state.error && <p role="alert">{state.error}</p>}{state.data?.recent_events.length ? <ul className="live-events">{state.data.recent_events.map(event => <li key={event.id}><span>{event.title}</span><time>{dateText(event.occurred_at)}</time></li>)}</ul> : <p>Sin eventos en los últimos {state.days} días.</p>}</section>;
}

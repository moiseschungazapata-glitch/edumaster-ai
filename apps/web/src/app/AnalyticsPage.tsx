import { useCallback, useEffect, useState } from 'react';
import { supabase } from './auth';

type Row = {
  date: string; course_id: string; enrollments: number; lesson_completions: number;
  assessment_passes: number; assessment_failures: number; active_actors: number;
};
type Report = {
  source: string; schema: string; version: string; generated_at: string; as_of: string | null;
  period_days: number; quality: { accepted: number; rejected: number; duplicate_ids: number; feature_rows: number };
  totals: { enrollments: number; lesson_completions: number; assessment_passes: number; assessment_failures: number };
  courses: { id: string; title: string }[]; rows: Row[];
};
const api = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');

async function authorizedFetch(path: string, signal?: AbortSignal): Promise<Response> {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('La sesión venció. Inicia sesión de nuevo.');
  const response = await fetch(`${api}/api/v1/analytics${path}`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail || `No se pudo consultar la analítica (${response.status}).`);
  }
  return response;
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [courseId, setCourseId] = useState('');
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const path = `?days=${days}${courseId ? `&course_id=${encodeURIComponent(courseId)}` : ''}`;
  const reload = useCallback(async (signal?: AbortSignal) => {
    const response = await authorizedFetch(`/report${path}`, signal);
    const next = await response.json() as Report;
    if (!signal?.aborted) { setData(next); setError(''); }
  }, [path]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void reload(controller.signal).catch(e => {
      if (!controller.signal.aborted) setError((e as Error).name === 'TimeoutError'
        ? 'La base de datos tardó demasiado en responder.' : (e as Error).message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);

  const exportData = async () => {
    setExporting(true); setError('');
    try {
      const response = await authorizedFetch(`/export.csv${path}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = 'edumaster-analytics.csv'; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError((e as Error).message); }
    finally { setExporting(false); }
  };
  const title = new Map(data?.courses.map(c => [c.id, c.title]) ?? []);
  return <div className="analytics-page">
    <section className="panel academic-panel">
      <span className="panel-eyebrow">EVENTOS ACADÉMICOS · DATOS REALES</span>
      <h2>Reporte reproducible</h2>
      <div className="live-filters">
        <label>Período<select value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={7}>7 días</option><option value={30}>30 días</option><option value={90}>90 días</option>
        </select></label>
        <label>Curso<select value={courseId} onChange={e => setCourseId(e.target.value)}>
          <option value="">Todos los cursos</option>
          {data?.courses.map(c => <option value={c.id} key={c.id}>{c.title}</option>)}
        </select></label>
        <button className="outline-button" disabled={loading} onClick={() => { setLoading(true); void reload().catch(e => setError((e as Error).message)).finally(() => setLoading(false)); }}>Actualizar</button>
        <button className="primary-button" disabled={!data || loading || exporting || Boolean(error)} onClick={() => void exportData()}>
          {exporting ? 'Preparando…' : 'Descargar CSV'}
        </button>
      </div>
      {loading && <p role="status">Cargando analítica…</p>}
      {error && <p role="alert" className="academic-message academic-error">{error}</p>}
    </section>
    {data && !error && <>
      <div className="analytics-metrics">
        {[
          ['Matrículas', data.totals.enrollments],
          ['Lecciones completadas', data.totals.lesson_completions],
          ['Evaluaciones aprobadas', data.totals.assessment_passes],
          ['Evaluaciones respondidas sin aprobar', data.totals.assessment_failures],
        ].map(([label, value]) => <div className="panel academic-panel" key={label}><span>{label}</span><h2>{value}</h2></div>)}
      </div>
      <section className="panel academic-panel">
        <span className="panel-eyebrow">AGRUPADO POR DÍA UTC Y CURSO</span><h2>Actividad del período</h2>
        {data.rows.length ? <div className="table-wrap"><table><thead><tr>
          <th>Fecha</th><th>Curso</th><th>Matrículas</th><th>Lecciones</th>
          <th>Aprobadas</th><th>Sin aprobar</th><th>Participantes activos</th>
        </tr></thead><tbody>{data.rows.map(row => <tr key={row.date + row.course_id}>
          <td>{row.date}</td><td>{title.get(row.course_id) || row.course_id}</td>
          <td>{row.enrollments}</td><td>{row.lesson_completions}</td>
          <td>{row.assessment_passes}</td><td>{row.assessment_failures}</td><td>{row.active_actors}</td>
        </tr>)}</tbody></table></div> : <p>No hay acciones académicas registradas en este período.</p>}
      </section>
      <section className="panel academic-panel">
        <h2>Origen y calidad</h2>
        <p>Fuente: {data.source} · Último evento: {data.as_of ? new Date(data.as_of).toLocaleString('es-PE') : 'sin eventos'}.</p>
        <p>Eventos válidos: {data.quality.accepted} · Rechazados: {data.quality.rejected} · Duplicados: {data.quality.duplicate_ids}.</p>
        <p>Esquema: {data.schema} · Versión SHA-256: <code>{data.version}</code></p>
        <p>Este reporte agrupa eventos registrados desde la fase 3. No reconstruye historial anterior a esa migración.</p>
      </section>
    </>}
  </div>;
}

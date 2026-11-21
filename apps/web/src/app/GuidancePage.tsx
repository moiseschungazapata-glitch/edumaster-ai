import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { supabase, type Profile } from './auth';

type Suggestion = {
  id: string; course_id: string; course_title: string; kind: string;
  source: string; model_version: null; rationale: string; evidence: string;
  expected_impact: string; priority: number; status: string;
  review_status: string; review_note: string; feedback_useful: boolean | null;
  created_at: string; expires_at: string; student_id?: string;
};
type Answer = { answer: string; explanation: string; source: string; course_id: string | null; model_version: null };
type ResponseList = { recommendations: Suggestion[]; summary?: { total: number; accepted: number; useful: number } };
const api = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('Tu sesión venció. Inicia sesión otra vez.');
  const response = await fetch(`${api}/api/v1/guidance${path}`, {
    method,
    signal: AbortSignal.timeout(15000),
    headers: { Authorization: `Bearer ${session.access_token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(problem?.detail || `No se pudo completar la acción (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

const statusText: Record<string, string> = {
  new: 'Nueva', accepted: 'Aceptada', discarded: 'Descartada',
  completed: 'Completada', expired: 'Expirada',
};
const reviewText: Record<string, string> = {
  pending: 'Pendiente de revisión docente',
  approved: 'Revisada y aprobada',
  rejected: 'Descartada por revisión docente',
};

export default function GuidancePage({ section, profile, onNavigate }: {
  section: 'tutor' | 'recommendations'; profile: Profile; onNavigate: (id: string) => void;
}) {
  const student = profile.role === 'student';
  const [items, setItems] = useState<Suggestion[]>([]);
  const [summary, setSummary] = useState<ResponseList['summary']>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [answer, setAnswer] = useState<Answer | null>(null);
  const reload = useCallback(async () => {
    const result = await request<ResponseList>(student ? '/recommendations' : '/reviews');
    setItems(result.recommendations); setSummary(result.summary);
  }, [student]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void reload().catch(e => { if (active) setError((e as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await action(); await reload(); }
    catch (e) { setError((e as Error).name === 'TimeoutError'
      ? 'La API tardó demasiado en responder.' : (e as Error).message); }
    finally { setBusy(false); }
  };
  const ask = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => setAnswer(await request<Answer>('/tutor', 'POST', { question })));
  };
  if (!student && !['teacher', 'coordinator', 'admin', 'superadmin'].includes(profile.role)) {
    return <p role="alert">Esta sección requiere una cuenta académica autorizada.</p>;
  }
  return <div className="guidance-page">
    <section className="panel academic-panel">
      <span className="panel-eyebrow">ORIENTACIÓN ACADÉMICA · {student ? 'ESTUDIANTE' : 'REVISIÓN DOCENTE'}</span>
      <h2>{section === 'tutor' ? 'Guía de aprendizaje' : student ? 'Tus sugerencias' : 'Sugerencias para revisar'}</h2>
      <p>Fuente: reglas académicas y progreso guardado. El modelo neuronal DEMO no emite predicciones ni calificaciones.</p>
      {student && section === 'recommendations' && <button className="primary-button" disabled={busy}
        onClick={() => void run(() => request('/recommendations/refresh', 'POST'))}>Buscar sugerencias</button>}
      {section === 'tutor' && student && <form className="guidance-question" onSubmit={ask}>
        <label htmlFor="guidance-question">Pregunta por tus cursos o qué estudiar después</label>
        <div><input id="guidance-question" value={question} minLength={2} maxLength={500}
          onChange={e => setQuestion(e.target.value)} placeholder="¿Qué curso puedo seguir?" required/>
          <button className="primary-button" disabled={busy}>Consultar</button></div>
      </form>}
      {answer && section === 'tutor' && <div className="academic-message" role="status">
        <strong>Orientación basada en datos</strong><p>{answer.answer}</p><small>{answer.explanation}</small>
        {answer.course_id && <p><button className="text-link" onClick={() => onNavigate('courses')}>Ir a cursos →</button></p>}
      </div>}
      {section === 'tutor' && student && <button className="text-link"
        onClick={() => onNavigate('recommendations')}>Ver todas mis sugerencias →</button>}
      {section === 'tutor' && !student && <button className="text-link"
        onClick={() => onNavigate('recommendations')}>Revisar sugerencias de mis cursos →</button>}
      {loading && <p role="status">Cargando sugerencias…</p>}
      {error && <div role="alert" className="academic-message academic-error">{error}</div>}
    </section>
    {section === 'recommendations' && <>
      {!student && summary && <div className="panel academic-panel">
        Revisadas y activas: {summary.accepted} · Marcadas útiles: {summary.useful} · Total mostrado: {summary.total}.
      </div>}
      <div className="academic-grid">
        {items.map(item => <article className="panel academic-panel" key={item.id}>
          <span className="panel-eyebrow">{item.source} · {item.course_title}</span>
          <h2>{item.rationale}</h2>
          <p><strong>Evidencia:</strong> {item.evidence}</p>
          <p><strong>Posible beneficio:</strong> {item.expected_impact}</p>
          <p>{statusText[item.status] || item.status} · {reviewText[item.review_status] || item.review_status}</p>
          <small>Creada: {new Date(item.created_at).toLocaleString('es-PE')} · Vence: {new Date(item.expires_at).toLocaleDateString('es-PE')}</small>
          {item.review_note && <p>Nota docente: {item.review_note}</p>}
          {!student && <small>Estudiante: {item.student_id?.slice(0, 8)}…</small>}
          <div className="guidance-actions">
            {!student && item.review_status === 'pending' && item.status === 'new' && <>
              <label className="guidance-review-note">Nota de revisión (opcional)
                <textarea value={reviewNotes[item.id] || ''} maxLength={500}
                  onChange={e => setReviewNotes(old => ({ ...old, [item.id]: e.target.value }))}/>
              </label>
              <button className="primary-button" disabled={busy} onClick={() => void run(() =>
                request(`/reviews/${item.id}`, 'POST', { decision: 'approve', note: reviewNotes[item.id] || '' }))}>Aprobar</button>
              <button className="outline-button" disabled={busy} onClick={() => void run(() =>
                request(`/reviews/${item.id}`, 'POST', { decision: 'reject', note: reviewNotes[item.id] || '' }))}>Descartar</button>
            </>}
            {student && item.review_status === 'approved' && item.status === 'new' && <>
              <button className="primary-button" disabled={busy} onClick={() => void run(() =>
                request(`/recommendations/${item.id}/action`, 'POST', { action: 'accept' }))}>Aceptar</button>
              <button className="outline-button" disabled={busy} onClick={() => void run(() =>
                request(`/recommendations/${item.id}/action`, 'POST', { action: 'discard' }))}>Descartar</button>
            </>}
            {student && item.status === 'accepted' && <>
              <button className="outline-button" disabled={busy} onClick={() => void run(() =>
                request(`/recommendations/${item.id}/action`, 'POST', { action: 'complete' }))}>Marcar realizada</button>
            </>}
            {student && ['accepted', 'completed'].includes(item.status) && item.review_status === 'approved' && <>
              <button className="text-link" disabled={busy} onClick={() => void run(() =>
                request(`/recommendations/${item.id}/feedback`, 'POST', { useful: true }))}>Fue útil</button>
              <button className="text-link" disabled={busy} onClick={() => void run(() =>
                request(`/recommendations/${item.id}/feedback`, 'POST', { useful: false }))}>No fue útil</button>
              {item.feedback_useful !== null && <small>Tu opinión: {item.feedback_useful ? 'útil' : 'no útil'}</small>}
            </>}
          </div>
        </article>)}
      </div>
      {!loading && !items.length && <div className="panel academic-panel">
        {student ? 'Aún no tienes sugerencias. Pulsa «Buscar sugerencias» para revisar tus cursos.'
          : 'No hay sugerencias de tus cursos pendientes de revisión.'}
      </div>}
    </>}
  </div>;
}

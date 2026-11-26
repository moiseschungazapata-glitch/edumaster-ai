import { useCallback, useEffect, useState } from 'react';
import { apiBaseUrl, supabase, type Profile } from './auth';

type Certificate = { id: string; course_title: string; status: string; issued_at: string; student_id: string | null };

export async function downloadCertificate(id: string) {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('La sesión venció. Inicia sesión otra vez.');
  const response = await fetch(`${apiBaseUrl}/api/v1/certificates/${id}/pdf`, {
    headers: { Authorization: `Bearer ${session.access_token}` }, signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`No se pudo descargar el certificado (${response.status}).`);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `certificado-${id}.pdf`; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export default function CertificatesPage({ profile }: { profile: Profile }) {
  const [items, setItems] = useState<Certificate[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const editor = ['superadmin', 'admin', 'coordinator', 'teacher'].includes(profile.role);
  const load = useCallback(async () => {
    const token = (await supabase?.auth.getSession())?.data.session?.access_token;
    if (!token) throw new Error('Inicia sesión nuevamente.');
    const response = await fetch(`${apiBaseUrl}/api/v1/certificates`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error(`No se pudieron cargar los certificados (${response.status}).`);
    setItems(await response.json() as Certificate[]);
  }, []);
  useEffect(() => { void load().catch(e => setError((e as Error).message)).finally(() => setLoading(false)); }, [load]);
  const revoke = async (id: string) => {
    if (!window.confirm('¿Anular este certificado? Su código público dejará de ser válido.')) return;
    setBusy(true); setError('');
    try {
      const token = (await supabase?.auth.getSession())?.data.session?.access_token;
      const response = await fetch(`${apiBaseUrl}/api/v1/certificates/${id}/revoke`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error(`No se pudo anular (${response.status}).`);
      await load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <div className="academic-page">
    {error && <p className="academic-message academic-error" role="alert">{error}</p>}
    {loading && <p role="status">Cargando certificados…</p>}
    {!loading && !items.length && <div className="panel academic-panel">Todavía no hay certificados emitidos. Completa todas las lecciones y aprueba las evaluaciones de un curso para obtener uno.</div>}
    <div className="academic-grid">{items.map(item => <article className="panel academic-panel" key={item.id}>
      <span className="panel-eyebrow">{item.status === 'issued' ? 'CERTIFICADO VIGENTE' : 'CERTIFICADO ANULADO'}</span>
      <h2>{item.course_title}</h2><p>Emitido el {new Date(item.issued_at).toLocaleDateString('es-PE')}</p>
      {editor && item.student_id && <p>Estudiante: {item.student_id}</p>}
      {item.status === 'issued' && <button className="primary-button" disabled={busy} onClick={() => void downloadCertificate(item.id).catch(e => setError((e as Error).message))}>Descargar PDF</button>}
      {editor && item.status === 'issued' && <button className="outline-button" disabled={busy} onClick={() => void revoke(item.id)}>Anular certificado</button>}
      {editor && item.status === 'revoked' && <button className="outline-button" disabled={busy} onClick={() => void (async () => { setBusy(true); setError(''); try { const token = (await supabase?.auth.getSession())?.data.session?.access_token; const response = await fetch(`${apiBaseUrl}/api/v1/certificates/${item.id}/reissue`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error(`No se pudo reemitir (${response.status}).`); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } })()}>Reemitir certificado</button>}
    </article>)}</div>
  </div>;
}

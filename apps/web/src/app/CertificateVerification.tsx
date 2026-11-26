import { useEffect, useState } from 'react';
import { apiBaseUrl } from './auth';

type Verification = { valid: boolean; status: string; course: string; issued_at: string };

export default function CertificateVerification({ code }: { code: string }) {
  const [result, setResult] = useState<Verification | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!/^[A-Za-z0-9_-]{32}$/.test(code)) { setError('Código inválido.'); return; }
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/v1/certificates/verify/${code}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('No encontramos este certificado.'); return response.json() as Promise<Verification>; })
      .then(setResult).catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message); });
    return () => controller.abort();
  }, [code]);
  return <main className="academic-page" style={{ maxWidth: 680, margin: '5rem auto', padding: '1rem' }}>
    <section className="panel academic-panel"><span className="panel-eyebrow">EDUMASTER.AI · VERIFICACIÓN</span>
      <h1>Verificar certificado</h1>
      {!result && !error && <p role="status">Consultando el registro…</p>}
      {error && <p role="alert">{error}</p>}
      {result && <><h2>{result.valid ? 'Certificado vigente' : 'Certificado anulado'}</h2><p>Curso: {result.course}</p><p>Fecha de emisión: {new Date(result.issued_at).toLocaleDateString('es-PE')}</p></>}
    </section>
  </main>;
}

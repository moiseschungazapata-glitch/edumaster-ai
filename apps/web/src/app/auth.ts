const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const apiBaseUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || window.location.origin;
const storageKey = 'edumaster-supabase-session';

export const isConfigured = Boolean(url && key);
type Session = { access_token: string; refresh_token: string; expires_at: number };
type AuthEvent = 'SIGNED_IN' | 'SIGNED_OUT';
const subscribers = new Set<(event: AuthEvent) => void>();
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let inFlightRefresh: Promise<Session | null> | null = null;

function read(): Session | null {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null || !('access_token' in value) || !('refresh_token' in value) || !('expires_at' in value)) return null;
    const session = value as Session;
    return typeof session.access_token === 'string' && typeof session.refresh_token === 'string' && typeof session.expires_at === 'number' ? session : null;
  } catch { return null; }
}

function clear() {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = undefined;
  try { sessionStorage.removeItem(storageKey); } catch { /* Almacenamiento no disponible. */ }
  subscribers.forEach(callback => callback('SIGNED_OUT'));
}

function save(session: Session) {
  try { sessionStorage.setItem(storageKey, JSON.stringify(session)); } catch { /* Almacenamiento no disponible. */ }
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => { void refresh(); }, Math.max(1000, (session.expires_at - Date.now() / 1000 - 60) * 1000));
}

async function tokenRequest(grantType: 'password' | 'refresh_token', body: object): Promise<Session> {
  const response = await fetch(`${url}/auth/v1/token?grant_type=${grantType}`, {
    method: 'POST', headers: { apikey: key, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as { error_code?: string; code?: string; msg?: string };
    const code = problem.error_code ?? problem.code;
    if (code === 'email_not_confirmed' || /email not confirmed/i.test(problem.msg ?? '')) throw new Error('Confirma el correo de esta cuenta en Supabase antes de iniciar sesión.');
    if (response.status === 429) throw new Error('Demasiados intentos. Espera unos minutos y vuelve a probar.');
    if (response.status === 401 && code !== 'invalid_credentials') throw new Error('Revisa la clave pública y la URL de Supabase.');
    throw new Error('El correo o la contraseña no son correctos.');
  }
  const data: unknown = await response.json();
  if (typeof data !== 'object' || data === null || !('access_token' in data) || !('refresh_token' in data) || !('expires_in' in data)) throw new Error('Respuesta de autenticación incompleta.');
  const value = data as { access_token: string; refresh_token: string; expires_in: number };
  if (!value.access_token || !value.refresh_token || !Number.isFinite(value.expires_in)) throw new Error('Sesión inválida.');
  return { access_token: value.access_token, refresh_token: value.refresh_token, expires_at: Math.floor(Date.now() / 1000) + value.expires_in };
}

async function refresh(): Promise<Session | null> {
  if (inFlightRefresh) return inFlightRefresh;
  const previous = read();
  if (!previous) return null;
  inFlightRefresh = (async () => {
    try {
      const updated = await tokenRequest('refresh_token', { refresh_token: previous.refresh_token });
      save(updated);
      return updated;
    } catch { clear(); return null; }
    finally { inFlightRefresh = null; }
  })();
  return inFlightRefresh;
}

export const supabase = isConfigured ? {
  auth: {
    async signInWithPassword({ email, password }: { email: string; password: string }) {
      try {
        const session = await tokenRequest('password', { email, password });
        save(session);
        subscribers.forEach(callback => callback('SIGNED_IN'));
        return { data: { session }, error: null };
      } catch (error) { return { data: { session: null }, error }; }
    },
    async getSession() {
      const current = read();
      const session = current && current.expires_at <= Date.now() / 1000 + 60 ? await refresh() : current;
      if (session && !refreshTimer) save(session);
      return { data: { session }, error: null };
    },
    onAuthStateChange(callback: (event: AuthEvent) => void) {
      subscribers.add(callback);
      return { data: { subscription: { unsubscribe: () => subscribers.delete(callback) } } };
    },
    async signOut(_options?: { scope: 'local' }) {
      const current = read();
      clear();
      if (current) {
        void fetch(`${url}/auth/v1/logout?scope=local`, {
          method: 'POST', headers: { apikey: key, Authorization: `Bearer ${current.access_token}` },
        }).catch(() => undefined);
      }
      return { error: null };
    },
  },
} : null;

export type Profile = {
  id: string;
  email: string;
  role: string;
  institution_id: string | null;
};

export async function loadProfile(accessToken: string): Promise<Profile> {
  const response = await fetch(`${apiBaseUrl}/api/v1/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new Error(response.status === 401 ? 'La sesión venció. Inicia sesión otra vez.' : 'No se pudo verificar el perfil en la API.');
  return response.json() as Promise<Profile>;
}

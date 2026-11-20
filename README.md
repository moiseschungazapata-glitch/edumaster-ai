# EduMaster.ai

Monorepo de la plataforma educativa. La fase 1 incluye la base visual React, autenticación Supabase, API FastAPI, perfiles y roles en PostgreSQL, migración versionada, health checks y CI. Los módulos académicos, métricas e IA del dashboard todavía muestran datos **DEMO**; corresponden a las fases 2–6.

## Requisitos

- Node.js 22 o superior y Python 3.11 o superior.
- Proyecto Supabase con **JWT signing key asimétrica** activa (ES256 o RS256). La API valida sus tokens con el JWKS público; el JWT legacy HS256 no está habilitado.
- Acceso a la conexión PostgreSQL de ese proyecto (Database → Connect). Nunca pegues su contraseña ni claves secretas en el repositorio.

## Configurar Supabase (una vez)

1. Crea tu proyecto en Supabase y activa el proveedor **Email** en Authentication. En Authentication → Users crea tu usuario con una contraseña **nueva**. La contraseña antigua del prototipo estuvo en el frontend y debe considerarse expuesta.
2. En Authentication → Signing Keys, utiliza una llave asimétrica activa. Comprueba que `https://TU-PROYECTO.supabase.co/auth/v1/.well-known/jwks.json` contenga al menos una llave pública.
3. Copia `apps/web/.env.example` a `apps/web/.env.local`. Rellena la URL del proyecto y su **publishable key** pública. `VITE_API_URL` es la URL accesible de FastAPI, `http://localhost:8000` para desarrollo.
4. Copia `apps/api/.env.example` a `apps/api/.env`. Rellena `SUPABASE_URL`, la URL de conexión **PostgreSQL** y los orígenes permitidos del frontend. La URL debe comenzar con `postgresql+psycopg://`; codifica los caracteres especiales de la contraseña.
5. Aplica la migración como se indica abajo. La migración incorpora usuarios existentes y el trigger incorpora usuarios nuevos.
6. Para habilitar el panel de administración, asigna el primer rol desde el **SQL Editor** de Supabase (solo un administrador autorizado). Comprueba `SELECT id, email, role FROM public.profiles;` y ejecuta `UPDATE public.profiles SET role = 'superadmin' WHERE id = 'EL-UUID-VERIFICADO';`. No existe un endpoint público para elevar privilegios.

La llave publishable puede llegar al navegador; **jamás** uses una service role key, secret key, contraseña PostgreSQL ni JWT signing secret con prefijo `VITE_`. Las tablas `profiles` e `institutions` tienen RLS activado sin políticas de acceso directo desde el navegador. La API consulta mediante PostgreSQL y aplica permisos en el servidor. La conexión privilegiada queda únicamente en el backend.

## Desarrollo local (PowerShell)

```powershell
cd C:\edumaster-ai\apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

En una **segunda terminal**:

```powershell
cd C:\edumaster-ai\apps\web
npm.cmd install
npm.cmd run dev
```

Si `py -3.12` no está instalado, usa tu Python 3.11+ para crear `.venv`. No uses la URL de Vercel como `VITE_API_URL` hasta que FastAPI esté desplegada en un servicio accesible. Servir React en Vercel no despliega automáticamente la API.

### Comprobar

- `http://localhost:8000/health/live` devuelve `{"status":"ok"}`.
- `http://localhost:8000/health/ready` devuelve `{"status":"ready"}` después de configurar PostgreSQL.
- `http://localhost:8000/docs` muestra OpenAPI.
- En `http://localhost:5173`, inicia sesión con el usuario creado en Supabase. Recargar conserva la sesión; cerrar sesión la elimina. Sin token válido, `/api/v1/me` responde 401; sin rol admin, `/api/v1/admin/ping` responde 403.

## Calidad y ambientes

```powershell
cd C:\edumaster-ai\apps\api
.\.venv\Scripts\python.exe -m pytest -q
cd C:\edumaster-ai\apps\web
npm.cmd run build
```

GitHub Actions verifica ambas aplicaciones en cada push y pull request. Configura variables independientes para **local**, **staging** y **producción**; aplica `alembic upgrade head` antes de desplegar la API compatible. Agrega cada origen web a `CORS_ORIGINS` y usa HTTPS públicamente. `.env`/`.env.local` están ignoradas por Git. La API registra `request_id`, estado y duración sin tokens; `/health/live` y `/health/ready` sirven para observación. La fase 7 ampliará monitoreo, pruebas de carga, auditoría y recuperación.

## Estructura

- `apps/web/src/app/`: shell visual, login y cliente de autenticación.
- `apps/api/app/core/`: configuración, modelos, base de datos y autorización.
- `apps/api/alembic/`: migración de instituciones, perfiles y trigger de usuario.
- `apps/api/tests/`: pruebas de acceso y roles.
- `.github/workflows/ci.yml`: compilación web y pruebas de API.

**Límite de fase:** el login y los permisos de API son reales una vez configurado Supabase; las pantallas de cursos, analítica, recomendaciones y la red neuronal siguen siendo ilustrativas.

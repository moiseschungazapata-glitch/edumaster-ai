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

## Fase 2: núcleo académico

La migración `0002_academic` crea cursos, lecciones, rutas ordenadas, matrículas, evaluaciones de opción múltiple, intentos y progreso. Una vez configurada la fase 1, ejecuta `alembic upgrade head` desde `apps/api` y reinicia FastAPI. Los estudiantes ven cursos publicados de su institución, se inscriben, leen lecciones, las completan y responden evaluaciones; el servidor calcula la nota y el porcentaje de avance. Los docentes crean borradores, añaden lecciones y evaluaciones, crean rutas y publican; un curso con matrículas no puede volver a borrador. Los administradores y coordinadores pueden gestionar los cursos de su institución. Las rutas solo incluyen cursos visibles para el usuario.

Para probar con dos cuentas, crea una institución y asigna el mismo UUID al perfil de un docente y al de un estudiante en el SQL Editor (ajusta los UUID tras comprobar `SELECT id,email,role,institution_id FROM public.profiles`):

```sql
INSERT INTO public.institutions (id, name) VALUES (gen_random_uuid(), 'Institución DEMO') RETURNING id;
UPDATE public.profiles SET role = 'teacher', institution_id = 'UUID-DE-LA-INSTITUCION' WHERE id = 'UUID-DEL-DOCENTE';
UPDATE public.profiles SET role = 'student', institution_id = 'UUID-DE-LA-INSTITUCION' WHERE id = 'UUID-DEL-ESTUDIANTE';
```

Abre web y API, entra como docente y crea un curso con una lección y una evaluación; publícalo y crea una ruta. Entra como estudiante, inscríbete, completa la lección y aprueba la evaluación. Recarga: el porcentaje y los intentos siguen guardados. Prueba también que otra institución no vea ese curso. Ejecuta `python -m pytest -q` en `apps/api` y `npm.cmd run build` en `apps/web`. No pongas contraseñas en SQL ni en Git.

**Límite de fase 2:** el login y los permisos de API necesitan la configuración real de Supabase. Cursos, rutas y evaluaciones consultan datos guardados. Las fases siguientes conectan el dashboard y los módulos de IA.

## Fase 3: dashboard y eventos en tiempo real

Después de configurar la fase 1 y aplicar la fase 2, ejecuta `alembic upgrade head` nuevamente: `0003_dashboard_events` añade fechas a matrículas, lecciones completadas e intentos, y crea un registro de eventos con acceso restringido al servidor. Las acciones académicas nuevas escriben el evento en la misma transacción. Los registros anteriores a esta migración reciben la fecha de la migración; su actividad histórica no puede reconstruirse.

`GET /api/v1/dashboard?days=7|30|90&course_id=UUID` devuelve indicadores, siete intervalos de actividad y eventos recientes, siempre limitados por institución y rol. `course_id` es opcional. Los estudiantes solo ven su actividad; los docentes, los cursos que imparten; administradores y coordinadores, su institución. La respuesta contiene `source` y `generated_at`. El porcentaje de finalización toma las matrículas creadas durante el periodo y considera completada una matrícula cuando todas sus lecciones están hechas y todas sus evaluaciones aprobadas. Los cursos publicados son el total actual; las demás tarjetas indican acciones o matrículas del periodo.

`GET /api/v1/dashboard/stream?after=ID` ofrece eventos SSE con token Bearer mediante `fetch` (EventSource estándar no envía el encabezado Authorization). El navegador reconecta con el último ID recibido y además consulta el resumen cada minuto si no hay conexión persistente. En producción, el proxy de la API debe permitir respuestas SSE sin buffering y mantener la conexión abierta. Para verificarlo, entra como docente y estudiante, crea un curso, inscríbete y completa una lección: el resumen y la campana se actualizan en ambas sesiones sin recargar. Revisa los filtros de periodo y curso, y comprueba que un usuario de otra institución no vea sus datos. Ejecuta `python -m pytest -q` en `apps/api` y `npm.cmd run build` en `apps/web`.

Dashboard, analítica y actividad muestran datos académicos guardados. Los módulos de mapa de habilidades, IA, recomendaciones y certificados siguen marcados como DEMO hasta fases posteriores.

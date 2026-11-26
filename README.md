# EduMaster.ai

Monorepo de la plataforma educativa. La fase 1 incluye la base visual React, autenticación Supabase, API FastAPI, perfiles y roles en PostgreSQL, migración versionada, health checks y CI. El núcleo académico, el dashboard y la analítica consultan datos guardados; el tutor de IA, las recomendaciones y las habilidades siguen como **DEMO** hasta sus fases posteriores.

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

Para verificar **solo la integración con Supabase** desde una terminal con acceso a internet, ejecuta en `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_supabase
```

La comprobación es de solo lectura y no muestra contraseñas, tokens ni correos. Compara los proyectos de web, API y PostgreSQL; consulta las claves públicas de autenticación; y comprueba la migración `0005_audit`, las tablas y RLS. Si falla por conectividad, ejecútala desde tu PC con internet. Una salida correcta aún requiere iniciar sesión como docente y estudiante y probar un curso, una matrícula y la persistencia tras recargar; estas operaciones no se realizan automáticamente.

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

Dashboard y actividad muestran datos académicos guardados. La analítica de dataset se implementa en la fase 4. Los módulos de mapa de habilidades, IA, recomendaciones y certificados siguen marcados como DEMO hasta fases posteriores.

## Fase 4: dataset y analítica

La sección **Analítica educativa** consulta eventos reales de la institución, filtra por 7/30/90 días y curso y permite descargar un CSV agregado por día UTC y curso. Incluye matrícula, lecciones terminadas, evaluaciones aprobadas/no aprobadas y número de participantes activos por día. Muestra fuente, última actividad, versión SHA-256 y control de calidad. El acceso está limitado por institución: el estudiante ve sus propias acciones; el docente, sus cursos; administradores, coordinadores, analistas y auditores, su institución. La descarga no contiene correos ni identificadores de estudiantes. La API ofrece `GET /api/v1/analytics/report` y `GET /api/v1/analytics/export.csv`, ambos con token Bearer.

El pipeline independiente usa el mismo esquema `academic-daily-v1` que el reporte. El dataset sintético de ejemplo está en `apps/api/data/demo_events.jsonl`, identificado explícitamente como DEMO. Ejecútalo desde `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m app.dataset --source demo --out ..\..\data\analytics\demo
```

Para generar una instantánea de datos reales **solo de una institución autorizada**, con el backend configurado y migrado, usa:

```powershell
.\.venv\Scripts\python.exe -m app.dataset --source database --institution UUID-DE-TU-INSTITUCION --out ..\..\data\analytics\real
```

Cada ejecución escribe `daily_course_features.csv` y `manifest.json` en la carpeta indicada. El manifiesto documenta fuente, esquema, zona UTC, columnas, fecha máxima, volumen aceptado/rechazado, duplicados y hash del CSV. Mismo contenido produce la misma versión y los archivos generados en `data/analytics/` están ignorados por Git. La validación rechaza tipo de evento desconocido, identificadores inválidos, marca de tiempo sin zona, acciones sin curso e IDs repetidos; ante errores no escribe la instantánea. Los eventos anteriores a la fase 3 no tienen historial reconstruible. No se entrena un modelo ni se hacen recomendaciones en esta fase.

Para cerrar fase 4, ejecuta `pytest -q` y `npm run build`; abre **Analítica educativa** con docente y estudiante y verifica filtros, totales, calidad y CSV. Prueba aislamiento con otra institución y confirma que el hash del manifiesto DEMO es idéntico al ejecutar dos veces. La base Supabase requiere la migración de fase 3, sin nueva migración en fase 4.

## Fase 5: modelo neuronal candidato (sin uso en producción)

El pipeline offline de `app.ml.train` entrena una GRU PyTorch con una capa de fusión, LayerNorm y Dropout y cuatro cabezas: finalización, dominio en tres niveles, riesgo y ranking de tres recursos. Usa semillas fijas, normalización calculada **solo** con entrenamiento, separación temporal con purga de etiquetas futuras, regularización, scheduler y parada temprana. Compara resultados contra prevalencias del entrenamiento; evalúa ROC-AUC, PR-AUC, F1, recall, Brier, calibración y FPR para tareas binarias; macro-F1, balanced accuracy, MAE y confusión para dominio; NDCG@3, Recall@2 y cobertura para ranking. Reporta métricas por segmento.

Instala las dependencias opcionales en el entorno API (pueden ocupar varios cientos de MB):

```powershell
cd C:\edumaster-ai\apps\api
uv pip install --python .\.venv\Scripts\python.exe ".[ml]"
.\.venv\Scripts\python.exe -m app.ml.train --source demo --out ..\..\data\models\demo
```

La ejecución DEMO genera `candidate.pt` (pesos y transformadores), `evaluation.json` (baseline y métricas), `history.json` (curvas), `model_card.md` (limitaciones) y `registry.json` (versión y estado no promovido). Registra parámetros, commit, métricas y artefactos en MLflow con SQLite local en `data/models/mlruns/`; esas salidas están ignoradas por Git. El comando imprime la versión SHA-256 del modelo y se puede repetir con el mismo `--seed` para comprobarla. La app sigue mostrando la red animada como **DEMO**: no está conectada a inferencia.

**Datos reales:** el CSV agregado de fase 4 contiene una sola fila en la institución de prueba y no incluye objetivos futuros por estudiante. No sirve para entrenamiento supervisado. El modo `--source labeled --data ruta.jsonl --out ..\..\data\models\real` exige un archivo autorizado de al menos 100 alumnos con una instantánea por alumno. Cada línea JSONL debe seguir el esquema `student-sequence-supervised-v1`: `student_key` seudónimo único, `segment`, `as_of`, `feature_window_end`, `label_observed_at` con zona horaria, `sequence` de seis vectores de cuatro números [0,1] en el orden `progress,assessment,visits,inactive_days`, y `labels` con `completion` y `risk` binarios, `mastery` y `next_resource` entre 0 y 2. Las variables deben preceder al corte y las etiquetas deben madurar después. El pipeline bloquea duplicados, fechas futuras, falta de diversidad de clases, conjuntos demasiado pequeños y solapamiento temporal entre entrenamiento/validación/test. No uses datos personales ni un dataset que no esté autorizado para esta finalidad.

El candidato real permanece `candidate_pending_human_review` incluso si mejora al baseline. La revisión técnica, docente, de privacidad, estabilidad y equidad por segmentos es necesaria antes de promoverlo a staging/shadow. No hay endpoint de inferencia, entrenamiento automático, publicación, calificaciones definitivas ni sanciones en esta fase. Con los datos actuales, solo está validado el **pipeline DEMO**; no es correcto declarar un modelo real listo para producción.

## Fase 6: orientación y recomendaciones supervisadas

Aplica la migración `0004_guidance` desde `apps/api` y reinicia la API:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

La nueva tabla `recommendations` tiene RLS activado, sin políticas de acceso directo desde el navegador. El estudiante pulsa **Buscar sugerencias** en la sección **Recomendaciones**: la API usa cursos publicados, matrículas, lecciones y evaluaciones de su institución, guarda motivo, evidencia, impacto cualitativo, prioridad y vencimiento. La sugerencia aparece `pending` hasta que el docente de ese curso, o un coordinador/administrador institucional, la aprueba o rechaza con una nota opcional. El estudiante puede entonces aceptar, descartar o marcar realizada la sugerencia y dejar feedback útil/no útil. Los estados y la opinión persisten; la revisión docente ve aceptación y utilidad agregadas. El tutor de esta fase responde solo a preguntas sobre cursos y sugerencias aprobadas mediante reglas, sin enviar texto libre a un proveedor de IA.

Los endpoints están bajo `/api/v1/guidance`: `POST/GET /recommendations` (el POST es `/recommendations/refresh`), `POST /recommendations/{id}/action`, `POST /recommendations/{id}/feedback`, `GET /reviews`, `POST /reviews/{id}` y `POST /tutor`. Requieren token Bearer, usan permisos y relación con institución/curso en la API; no aceptan identidad del estudiante desde el cliente. `GET /model/status` deja constancia de que el único modelo está en estado `demo_only` y `POST /model/predict` devuelve 503. No hay scores neuronales, calificaciones ni impacto numérico inventado en las recomendaciones de reglas.

Prueba con dos cuentas: como estudiante, pulsa **Buscar sugerencias**; como docente, abre **Recomendaciones** y aprueba una sugerencia de tu curso; como estudiante, acepta, marca realizada y vota su utilidad; recarga y comprueba persistencia. Una tercera institución no debe poder revisar ni modificar esa sugerencia. Las pruebas automáticas cubren estos permisos y el bloqueo de inferencia del modelo DEMO.

**Puerta de salida pendiente:** para convertir esto en inferencia neuronal y recomendaciones personalizadas validadas, primero hace falta una cohorte real etiquetada y autorizada, evaluación offline y segmentada, aprobación técnica y docente, una prueba controlada en staging/shadow, monitoreo y rollback. El dataset real actual tiene una sola fila agregada, de modo que la fase 6 no puede darse por completa como IA predictiva en producción. El estado de reglas y su feedback sí puede probarse ahora.

## Fase 7: endurecimiento

Los controles de auditoría, límite local de solicitudes y cabeceras de seguridad se describen junto con las pruebas de aceptación y recuperación en [la guía de fase 7](docs/phase7.md). Aplica la migración `0005_audit` con `alembic upgrade head` en tu entorno de pruebas antes de iniciar la API actualizada. La fase no se considera aceptada hasta completar los ensayos en staging y resolver las dependencias de datos reales e IA de las fases anteriores.

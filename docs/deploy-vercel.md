# Publicar EduMaster.ai en dos proyectos Vercel

Si tu cuenta dispone de Vercel Services y prefieres un único proyecto y dominio, usa [la guía de un proyecto](deploy-vercel-one-project.md).

Esta configuración usa **dos proyectos Vercel** que importan el mismo repositorio de GitHub: una función FastAPI desde `apps/api` y la web Vite desde `apps/web`. Los datos y la autenticación permanecen en Supabase. Los archivos `.env` locales no se suben a Git: las variables de producción se cargan en los paneles de Vercel.

## 1. Comprobar antes de publicar

- Ejecuta `cd apps/api; .\.venv\Scripts\python.exe -m scripts.check_supabase` en tu PC. La migración esperada es `0005_audit`; si ya aparece, **no necesitas repetirla**.
- Comprueba que la rama `main` del repositorio en GitHub tiene `apps/api/vercel.json`, `apps/web/vercel.json`, el código de las dos aplicaciones y los cambios de esta guía. Los proyectos de Vercel construyen el commit de GitHub, no los archivos que solo están en tu PC.
- Elige nombres distintos para los proyectos, por ejemplo `edumaster-ai-api` y `edumaster-ai-web`. Sus dominios de producción reales se muestran en Vercel al crearlos; no los adivines.

## 2. Crear la API primero

En Vercel selecciona **Add New → Project**, importa `moiseschungazapata-glitch/edumaster-ai` y configura:

| Ajuste | Valor |
| --- | --- |
| Nombre | `edumaster-ai-api` u otro disponible |
| Root Directory | `apps/api` |
| Framework Preset | `FastAPI` si aparece; conserva la detección de `app.main:app` |
| Python | 3.12, declarada en `apps/api/.python-version` |
| Build/Output/Install Command | Valores automáticos; no uses `npm run build` en la API |

Antes del primer despliegue, en **Environment Variables**, configura para **Production**:

| Variable | Valor |
| --- | --- |
| `APP_ENV` | `production` |
| `SUPABASE_URL` | URL HTTPS del mismo proyecto que pasó `scripts.check_supabase` |
| `DATABASE_URL` | Puedes reutilizar la cadena de `apps/api/.env` que ya pasó `scripts.check_supabase` (session pooler, puerto 5432). En producción con más instancias se recomienda **Connect → Transaction pooler** (puerto 6543): cambia `postgresql://` por `postgresql+psycopg://` y agrega `?sslmode=require` al final si no existe. Usa la contraseña de la base codificada como URL, y nunca la pegues en Git ni en el frontend. |
| `CORS_ORIGINS` | Por ahora, una dirección HTTPS provisional propia que controlarás, por ejemplo el dominio de producción previsto de la web; en el paso 4 se cambia al dominio **real** de Vercel. No uses `*`, `http://localhost` ni una barra final. |

La API usa conexiones de corta vida y desactiva las consultas preparadas cuando corre en Vercel; esto es compatible con el transaction pooler (puerto 6543). También sirve el **session pooler** (puerto 5432) que ya usas localmente; para funciones con muchas instancias Supabase recomienda el transaction pooler. No ejecutes migraciones en cada invocación: ya se comprobó `0005_audit` en Supabase.

Pulsa **Deploy**. Copia el **dominio de producción** de la API, por ejemplo `https://edumaster-ai-api.vercel.app`. En el navegador verifica:

- `/health/live` devuelve `{"status":"ok"}`.
- `/health/ready` devuelve `{"status":"ready"}`. Si devuelve 503, revisa `DATABASE_URL` y los logs de la función; no expongas la contraseña en una captura.
- `/api/v1/me` sin iniciar sesión devuelve **401**. Eso es correcto.

## 3. Crear la web

En Vercel importa **el mismo repositorio** como *otro proyecto*:

| Ajuste | Valor |
| --- | --- |
| Nombre | `edumaster-ai-web` u otro disponible |
| Root Directory | `apps/web` |
| Framework Preset | `Vite` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

Configura estas variables para **Production** antes de pulsar **Deploy**:

| Variable | Valor |
| --- | --- |
| `VITE_SUPABASE_URL` | Misma URL pública del proyecto Supabase |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Clave **publishable** pública de ese proyecto (`sb_publishable_...`) |
| `VITE_API_URL` | Dominio HTTPS **real de la API del paso 2**, sin barra final ni `/api/v1` |

**Nunca** pongas `DATABASE_URL`, contraseña de PostgreSQL, `service_role` ni `secret key` en el proyecto web o una variable `VITE_`. La web es una SPA: `apps/web/vercel.json` hace que sus rutas carguen `index.html` al abrirlas o recargarlas.

## 4. Autorizar el dominio real de la web

Una vez que Vercel muestre el dominio de producción de la web, abre el proyecto **API** → **Settings → Environment Variables** y cambia `CORS_ORIGINS` a ese origen HTTPS exacto, por ejemplo `https://edumaster-ai-web.vercel.app`. Para un dominio propio, usa el dominio final. Puedes separar orígenes adicionales con comas, pero evita usar dominios de vista previa que cambian en cada despliegue.

**Vuelve a desplegar la API** para que tome la nueva variable. Si cambias una variable de la web, vuelve a desplegar **la web**: las variables `VITE_` se incorporan durante su compilación. Mantén `VITE_API_URL` sin `localhost` en producción.

## 5. Verificación de extremo a extremo

Desde el navegador abre la web publicada e inicia sesión con la cuenta docente. Crea un curso, una lección y una evaluación, y publícalo. En otra sesión inicia con el estudiante, matricúlate, completa la lección y responde la evaluación. Recarga la página: la sesión y el progreso deben persistir. El dashboard debe mostrar actividad; si el canal en vivo se reconecta, el resumen sigue consultándose periódicamente.

También puedes ejecutar desde `apps/api` la comprobación de publicación, sustituyendo los dominios por los **reales**:

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_release --api https://TU-API.vercel.app --web https://TU-WEB.vercel.app
```

La comprobación es de solo lectura y no requiere contraseñas. Tras un despliegue público, revisa el uso de la función FastAPI: el canal SSE conserva una conexión abierta durante unos 45 segundos y luego el navegador se reconecta. El limitador de solicitudes de la API es por instancia; para muchos usuarios hace falta protección compartida o en el borde. El benchmark OULAD se muestra como evaluación externa; publicarlo no habilita inferencia para estudiantes.

# Un proyecto Vercel para EduMaster.ai

Vercel **Services** permite desplegar la web Vite y FastAPI en un solo proyecto y dominio. Está en beta: primero comprueba que tu cuenta ofrece **Services** como Framework Preset. Si no aparece, hay que preparar otra configuración de proyecto único que sirva la web desde FastAPI; [la guía de dos proyectos](deploy-vercel.md) queda como opción disponible.

1. Ejecuta `cd apps/api; .\.venv\Scripts\python.exe -m scripts.check_supabase`. Tu proyecto ya mostró migración `0005_audit` y RLS habilitado; no vuelvas a ejecutar migraciones si sigue igual.
2. Sube el archivo `vercel.json` de la raíz y los demás cambios de este despliegue a tu repositorio GitHub. Vercel importa lo que está en GitHub, no los archivos locales.
3. En Vercel, **Add New → Project**, importa `moiseschungazapata-glitch/edumaster-ai`. Deja **Root Directory** en la raíz del repositorio (`.`); en **Framework Preset** selecciona **Services**. El `vercel.json` raíz configura la web y la API; la web responde en `/` y FastAPI en `/api/v1/` y `/health/`.
4. Antes de desplegar, en **Environment Variables → Production** configura:

   | Variable | Valor |
   | --- | --- |
   | `VITE_SUPABASE_URL` | URL HTTPS pública del proyecto Supabase verificado |
   | `VITE_SUPABASE_PUBLISHABLE_KEY` | Clave pública `sb_publishable_...` de ese proyecto |
   | `SUPABASE_URL` | La misma URL pública del proyecto |
   | `DATABASE_URL` | Cadena PostgreSQL de `apps/api/.env` que ya comprobaste (formato `postgresql+psycopg://...?...sslmode=require`), ingresada **solo** en Vercel |
   | `APP_ENV` | `production` |
   | `SAME_ORIGIN_ONLY` | `1` |

   **No configures** `VITE_API_URL` ni `CORS_ORIGINS`: el navegador llamará a la API en el mismo dominio. La base de datos sigue conectándose únicamente desde FastAPI. Nunca uses una clave `service_role`, contraseña PostgreSQL ni `DATABASE_URL` con prefijo `VITE_`. Para escalar funciones con muchas instancias, Supabase recomienda el *Transaction pooler* (puerto 6543); el código desactiva las consultas preparadas y usa conexiones de corta vida en Vercel.

5. Pulsa **Deploy**. Cuando termine, visita `https://TU-DOMINIO.vercel.app/health/live` (debe devolver `{"status":"ok"}`), `/health/ready` (debe devolver `{"status":"ready"}`) y `/api/v1/me` sin sesión (debe devolver 401). Abre la web en `/` y comprueba login docente y estudiante, curso, matrícula y recarga de sesión.
6. Desde `apps/api` puedes ejecutar ` .\.venv\Scripts\python.exe -m scripts.smoke_release --api https://TU-DOMINIO.vercel.app --web https://TU-DOMINIO.vercel.app` con el dominio real; es de solo lectura. Los cambios posteriores de variables requieren un nuevo despliegue.

El canal SSE de actividad se reconecta aproximadamente cada 45 segundos porque FastAPI corre como función; el dashboard mantiene su consulta periódica como respaldo. Vercel Services sigue sujeto a límites y uso de funciones. La vista neuronal muestra el benchmark OULAD evaluado offline; la inferencia para estudiantes sigue deshabilitada.

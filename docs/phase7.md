# Fase 7: endurecimiento y aceptación

Estado: **en progreso**. Esta guía registra evidencia local y verificaciones pendientes; no constituye una aprobación de producción.

## Alcance y evidencia local

- API: registro de solicitudes con identificador, duración y estado; salud `/health/live` y `/health/ready`.
- Cambios académicos y decisiones sobre recomendaciones: auditoría transaccional en `audit_records`; consulta paginada por límite desde `GET /api/v1/audit` para admin, coordinator, auditor o superadmin, siempre limitada a su institución. No se guardan contraseñas, tokens, contenido de la pregunta al tutor ni texto de notas en el registro.
- Cabeceras defensivas de API: `nosniff`, política de referentes, bloqueo de marcos, permisos, `no-store` en `/api/v1/`, HSTS en HTTPS. El sitio web desplegado requiere su propia política de cabeceras.
- Límite local: 120 peticiones por minuto por IP y método en `/api/v1/`, con respuesta 429 y `Retry-After`. Es un control **por proceso**, no protege un despliegue de múltiples instancias. Configurar un limitador compartido o en el borde antes de exposición pública; revisar la IP real solo mediante proxy de confianza.
- Automatización local: `cd apps/api; .\.venv\Scripts\python.exe -m pytest -q` y `cd apps/web; npm run build`. Las pruebas SQLite no reemplazan pruebas de RLS en PostgreSQL.

## Matriz de aceptación y amenazas

| Escenario | Control / verificación requerida | Estado |
| --- | --- | --- |
| Estudiante consulta datos de otra institución | Comprobar cursos, métricas, recomendaciones y auditoría con cuentas reales de dos instituciones | Parcial: pruebas de API para recomendaciones y auditoría; falta PostgreSQL/RLS |
| Estudiante ejecuta acción docente | Rechazo 403/404 de revisión y lectura de auditoría | Automatizado en API |
| Docente revisa curso de otro docente | Rechazo de revisión aunque compartan institución | Comprobar en staging con identidades reales |
| Suplantación / caducidad de JWT | Validar firma, audiencia, caducidad y rol tomado de perfil DB; probar token manipulado | Falta prueba de integración con Supabase |
| Ataque por carga o fuerza bruta | Límite de borde para login y API; métricas de 429 | Parcial: límite local API; login Supabase necesita control externo |
| Filtración de información | Inspeccionar logs, errores y backups; comprobar ausencia de secretos y datos personales | Revisión manual pendiente |
| Archivos e inyección | Probar carga de archivos si se habilita, dependencias y entradas SQL | Pendiente |
| Privacidad de sugerencias | Revisión humana, procedencia explícita y registro de decisiones | Implementado para reglas; IA real pendiente |

## Procedimiento para completar la aceptación

1. En `C:\edumaster-ai\apps\api`, aplicar ` .\.venv\Scripts\alembic.exe upgrade head` al entorno de pruebas con respaldo previo. Verificar `alembic current` = `0005_audit`; comprobar RLS habilitado y permisos efectivos en PostgreSQL para las credenciales usadas por API y cliente. La migración no se ejecuta automáticamente al iniciar la API.
2. Crear cuentas de prueba para dos instituciones y los roles student, teacher, admin y auditor. Recorrer la matriz de permisos, registrando petición, estado HTTP y captura sin credenciales. Verificar que un acceso inválido no crea evento de auditoría y que las operaciones aceptadas sí lo crean.
3. Revisar con teclado todas las páginas: foco visible, orden de tabulación, formularios con etiqueta y errores anunciados, contraste, móvil y zoom de 200 %. Ejecutar auditoría automática de accesibilidad y corregir hallazgos; registrar navegador y evidencia.
4. Ejecutar pruebas E2E de login, recarga de sesión, creación de curso, matrícula, evaluación, panel y ciclo completo de recomendación con datos de prueba. No usar estudiantes reales sin autorización.
5. Medir p50/p95 y errores de inicio de sesión, panel, cursos y recomendaciones bajo carga progresiva en staging. Definir metas con el equipo, conservar trazas y verificar que no se degrade PostgreSQL/Supabase. Simular desconexión y recuperación.
6. Preparar backup de staging; restaurarlo en una base aislada, ejecutar `alembic current`, verificar cantidad de registros y ensayar rollback de aplicación. No ejecutar `alembic downgrade` sobre la base productiva sin plan de pérdida de datos.
7. Registrar UAT con responsables, fecha, defectos y evidencia. Confirmar que fases 5 y 6 tienen datos reales autorizados, validación del modelo y aprobación humana antes de aceptar la parte predictiva. Actualmente el modelo es `demo_only` y la predicción responde 503: impide declarar el producto completo como release candidate con IA real.

## Recuperación y operación

- Si falla `/health/ready`, revisar conectividad DB, secretos y migraciones; usar `/health/live` para distinguir proceso activo de dependencia caída. Nunca registrar URLs de conexión con contraseñas.
- Antes de una actualización: backup verificado, versión de código y migración actual, responsables y ventana de recuperación. Si falla la actualización: detener tráfico, restaurar versión anterior compatible y comprobar consistencia. Para cambios de esquema incompatibles, restaurar copia aislada primero y coordinar recuperación de datos.
- Vigilar porcentaje de 5xx/429, latencia p95, fallos de conexión, crecimiento de tablas de eventos/auditoría y tiempos de respuesta de Supabase. Definir retención, exportación y acceso al registro de auditoría según requisitos de la institución.

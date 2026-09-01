# KettleBell Pro

Aplicacion Django para explorar ejercicios y rutinas con kettlebell.

## Correr con Docker Desktop

1. Abre Docker Desktop.
2. Ve a `Containers` o `Images` y usa la opcion para levantar un proyecto desde Compose, seleccionando este archivo:
   `docker-compose.yml`
3. Inicia el stack.
4. Abre la app en:
   `http://localhost:8001`

El stack crea cuatro servicios:

- `web`: Django + Gunicorn.
- `reminders`: despachador de recordatorios del plan adaptativo.
- `db`: PostgreSQL local.
- `adminer`: interfaz web para administrar la BD.

Al iniciar, `web` espera a PostgreSQL, ejecuta migraciones y recolecta archivos estaticos automaticamente.

El endpoint `http://localhost:8001/healthz/` devuelve el estado de la aplicacion,
PostgreSQL y el SHA publicado. El healthcheck del contenedor usa este endpoint.

## Accesos

- App: `http://localhost:8001`
- PostgreSQL desde tu PC: `localhost:5433`
- Adminer: `http://localhost:8081`

La app web, PostgreSQL y Adminer quedan ligados a `127.0.0.1`; no se publican
directamente en la red. El Cloudflare Tunnel puede usar el puerto local `8001`
como única entrada externa.

Credenciales de PostgreSQL (toma el password real desde `.env`):

- Sistema en Adminer: `PostgreSQL`
- Servidor: `db`
- Usuario: `kettlebell`
- Password: el valor de `POSTGRES_PASSWORD`
- Base de datos: `kettlebell`

## Datos locales

La base de datos vive en el volumen Docker `postgres_data`, separado del `db.sqlite3` del proyecto. Esto permite simular mejor un entorno productivo local con PostgreSQL.

El contenedor expone PostgreSQL en el puerto local `5433` para no chocar con otras bases locales que ya usen `5432`.

El servicio `reminders` revisa cada minuto las sesiones pendientes cuyo recordatorio está vencido. Para recibir avisos push define `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` y `VAPID_ADMIN_EMAIL` en `.env`; si no están configuradas, el plan continúa funcionando con avisos dentro de la aplicación.

El volumen `postgres_data` contiene los datos. No lo elimines en una instalación
con datos sin exportar antes un backup verificable.

## Beta privada

En el servidor configura `DJANGO_ALLOW_REGISTRATION=False` y crea las cuentas
desde `/admin/`. El acceso externo recomendado es un Cloudflare Tunnel hacia
`127.0.0.1:8001`, protegido con Cloudflare Access y una allowlist de correos de
los testers. Define también `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_ENABLE_HTTPS` y
`KETTLEBELL_RELEASE_SHA` en el entorno del servidor.

El reproductor conserva durante siete días un borrador local por usuario/rutina.
Si falla el envío, mantiene el mismo `client_session_id` y reintenta al volver la
conexión; el servidor evita duplicados. Las páginas autenticadas y las APIs no se
guardan en la caché persistente del service worker y devuelven cabeceras HTTP
`private, no-store`.

## Historial y progreso

Los usuarios autenticados pueden consultar `/progress/` para revisar sus sesiones,
filtrar por periodo, origen o ejercicio y abrir el detalle de cada entrenamiento.
Las métricas y notas se pueden corregir sin cambiar la fecha, la rutina ni el plan;
la última edición queda registrada y alimenta las siguientes recomendaciones.

## Variables

El Compose ya trae valores locales por defecto. Si quieres cambiarlos, usa `.env.example` como referencia.

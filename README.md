# KettleBell Pro

Aplicacion Django para explorar ejercicios y rutinas con kettlebell.

## Correr con Docker Desktop

1. Abre Docker Desktop.
2. Ve a `Containers` o `Images` y usa la opcion para levantar un proyecto desde Compose, seleccionando este archivo:
   `docker-compose.yml`
3. Inicia el stack.
4. Abre la app en:
   `http://localhost:8000`

El stack crea dos servicios:

- `web`: Django + Gunicorn.
- `db`: PostgreSQL local.
- `adminer`: interfaz web para administrar la BD.

Al iniciar, `web` espera a PostgreSQL, ejecuta migraciones y recolecta archivos estaticos automaticamente.

## Accesos

- App: `http://localhost:8000`
- PostgreSQL desde tu PC: `localhost:5433`
- Adminer: `http://localhost:8081`

Credenciales de PostgreSQL:

- Sistema en Adminer: `PostgreSQL`
- Servidor: `db`
- Usuario: `kettlebell`
- Password: `kettlebell`
- Base de datos: `kettlebell`

## Datos locales

La base de datos vive en el volumen Docker `postgres_data`, separado del `db.sqlite3` del proyecto. Esto permite simular mejor un entorno productivo local con PostgreSQL.

El contenedor expone PostgreSQL en el puerto local `5433` para no chocar con otras bases locales que ya usen `5432`.

Para reiniciar la base desde cero, elimina el volumen `postgres_data` desde Docker Desktop y vuelve a iniciar el stack.

## Variables

El Compose ya trae valores locales por defecto. Si quieres cambiarlos, usa `.env.example` como referencia.

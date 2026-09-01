# Beta privada: checklist de servidor

Este runbook es deliberadamente manual. No sustituye una auditoría del host ni
ejecuta cambios por sí solo.

## 1. Auditar antes de migrar

Desde la carpeta del proyecto en el servidor:

```sh
docker compose ps
docker volume ls --filter name=postgres_data
docker compose config --quiet
docker compose exec web python manage.py showmigrations exercises
```

Confirma que el volumen de PostgreSQL, el contenedor y el SHA desplegado son los
esperados. Si hay datos, realiza un backup antes de cambiar la imagen:

```sh
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/kettlebell-$(date +%Y%m%d-%H%M%S).dump"
sha256sum backups/*.dump
docker compose exec -T db pg_restore --list < backups/ULTIMO.dump > backups/ULTIMO.list
```

Conserva el `.dump`, su checksum y la salida de `pg_restore --list` fuera del
volumen del contenedor.

## 2. Variables de la beta cerrada

Define en `.env` (sin subirlo al repositorio):

```dotenv
DJANGO_DEBUG=False
DJANGO_ALLOW_REGISTRATION=False
DJANGO_ALLOWED_HOSTS=tu-hostname.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://tu-hostname.example
DJANGO_ENABLE_HTTPS=True
KETTLEBELL_RELEASE_SHA=sha-del-release
```

El administrador crea las cuentas en `/admin/`. El Cloudflare Tunnel debe
apuntar a `http://127.0.0.1:8001`; Cloudflare Access limita el hostname a los
correos de la beta. PostgreSQL y Adminer permanecen en loopback.

## 3. Despliegue controlado

```sh
docker compose up -d --build
docker compose exec web python manage.py migrate --noinput
curl -fsS https://tu-hostname.example/healthz/
docker compose ps
```

La respuesta de `healthz` debe indicar `status=ok`, `database=ok` y el SHA
esperado. Comprueba también que `reminders` sigue activo después de reiniciar
el host. No borres `postgres_data` como mecanismo de actualización.

## 4. Prueba de aceptación de la beta

Con un teléfono Android, un iPhone y un PC verifica: inicio de sesión, creación
del plan, chequeo de preparación, dolor que bloquea la sesión, sesión acortada,
guardado normal, caída temporal de red con borrador y reintento, y ausencia de
duplicados. La app no promete entrenamiento médico: ante dolor se detiene y
recomienda buscar orientación profesional si persiste.

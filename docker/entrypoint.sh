#!/bin/sh
set -e

if [ -n "$POSTGRES_DB" ]; then
  python - <<'PY'
import os
import time
import psycopg

config = {
    "dbname": os.environ["POSTGRES_DB"],
    "user": os.environ["POSTGRES_USER"],
    "password": os.environ["POSTGRES_PASSWORD"],
    "host": os.getenv("POSTGRES_HOST", "db"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

for attempt in range(60):
    try:
        with psycopg.connect(**config):
            break
    except psycopg.OperationalError:
        if attempt == 59:
            raise
        time.sleep(1)
PY
fi

# Sembrar las imagenes del catalogo en el volumen de media sin pisar
# archivos ya existentes (subidas de usuarios o versiones previas).
if [ -d /app/media_seed ]; then
  cp -rn /app/media_seed/. /app/media/ || true
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"

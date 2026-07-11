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

python manage.py migrate --noinput
python manage.py seed_catalog
python manage.py collectstatic --noinput

exec "$@"

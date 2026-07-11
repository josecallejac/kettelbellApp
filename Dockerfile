FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/docker/entrypoint.sh

# Usuario sin privilegios; staticfiles se pre-crea con su owner para que el
# volumen nombrado herede los permisos y collectstatic pueda escribir.
RUN useradd --create-home appuser \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "kettelbell.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

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

# Copia de las imagenes del catalogo fuera de /app/media: el volumen de media
# monta encima de /app/media y ocultaria las que vienen en la imagen.
RUN cp -r /app/media /app/media_seed

RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "kettelbell.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

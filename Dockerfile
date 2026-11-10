# Imagen de producción para el rastreador de Tendry.
# Un solo worker de Gunicorn: el scheduler debe ejecutarse una sola vez.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Bogota \
    FLASK_DEBUG=0 \
    TRUST_PROXY=1 \
    DATABASE_URL=sqlite:////data/tendry.db \
    PORT=8000

# gosu permite arrancar como root, arreglar permisos del volumen y perder privilegios.
# tzdata es necesario para que la hora local se muestre correctamente.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu tzdata passwd \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

WORKDIR /app

COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

RUN mkdir -p /data /app/instance \
    && chown -R app:app /app /data \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# --workers 1 es intencional: evita dos schedulers y revisiones duplicadas.
# --threads 4 permite atender varias peticiones web mientras corre el bot.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "run:app"]

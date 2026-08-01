FROM python:3.14-slim

ENV APP_ENV=production \
    DEBUG=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend
COPY docker/entrypoint.sh /usr/local/bin/operations-entrypoint

RUN addgroup --system operations \
    && adduser --system --ingroup operations operations \
    && mkdir -p /app/backend/data \
    && chown -R operations:operations /app \
    && chmod 0755 /usr/local/bin/operations-entrypoint

WORKDIR /app/backend

ENTRYPOINT ["/usr/local/bin/operations-entrypoint"]
CMD ["python", "-m", "app.start"]

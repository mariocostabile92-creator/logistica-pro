FROM python:3.14-slim

ENV APP_ENV=production \
    DEBUG=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

RUN addgroup --system operations \
    && adduser --system --ingroup operations operations \
    && mkdir -p /app/backend/data \
    && chown -R operations:operations /app

USER operations
WORKDIR /app/backend

CMD ["python", "-m", "app.start"]

FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --base=/static/app/

FROM python:3.14-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings_production
WORKDIR /app
COPY backend/requirements*.txt ./backend/
RUN python -m pip install --no-cache-dir -r backend/requirements-production.txt
COPY backend/ ./backend/
COPY --from=frontend /build/frontend/dist ./frontend/dist/
COPY deploy/start.sh ./deploy/start.sh
# Build-only placeholders: collectstatic does not connect to a database.
# Runtime credentials are supplied by Render; none are persisted via ENV.
RUN DJANGO_SECRET_KEY=build-only-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ \
    DJANGO_ALLOWED_HOSTS=build.invalid \
    POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
    python backend/manage.py collectstatic --noinput
RUN useradd --uid 10001 --create-home lentis
USER lentis
EXPOSE 10000
CMD ["sh", "/app/deploy/start.sh"]

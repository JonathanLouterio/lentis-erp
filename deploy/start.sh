#!/bin/sh
set -eu
cd /app/backend
python manage.py check --deploy --fail-level ERROR
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -

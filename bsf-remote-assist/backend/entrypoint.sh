#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput
if [ "${BOOTSTRAP_ADMIN_ON_START:-true}" = "true" ]; then python manage.py bootstrap_admin; fi
exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout "${GUNICORN_TIMEOUT:-120}" --access-logfile - --error-logfile -

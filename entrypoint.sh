#!/usr/bin/env sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

: "${PORT:=8000}"
gunicorn sist_rec_api.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
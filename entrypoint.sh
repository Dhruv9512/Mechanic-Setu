#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# ✅ Wait for the database to become available
echo "Waiting for database..."
while ! python manage.py showmigrations &>/dev/null; do
    sleep 2
done

# ✅ Apply database migrations
echo "Applying database migrations..."
conda run --no-capture-output -n myenv python manage.py migrate --noinput

# ✅ Collect static files
echo "Collecting static files..."
conda run --no-capture-output -n myenv python manage.py collectstatic --noinput

# ✅ Start Daphne (ASGI Server) on port 8000 for both HTTP + WebSocket
echo "Starting Daphne (ASGI - WebSocket + HTTP)..."
conda run --no-capture-output -n myenv daphne -b 0.0.0.0 -p 8000 MechanicSetu.asgi:application &

# ✅ Start Celery Worker
echo "Starting Celery worker..."
exec conda run --no-capture-output -n myenv celery -A MechanicSetu worker \
  --loglevel=info \
  --pool=solo \
  --max-tasks-per-child=5 \
  --max-memory-per-child=100000

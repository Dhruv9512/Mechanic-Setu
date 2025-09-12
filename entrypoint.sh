#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# ✅ Activate Conda environment
echo "Activating Conda environment..."
conda run --no-capture-output -n myenv python -c "print('Conda environment activated.')"

# ✅ Wait for the database to become available
echo "Waiting for database to be ready..."
while ! conda run --no-capture-output -n myenv python manage.py showmigrations &>/dev/null; do
    echo "Database not ready, waiting..."
    sleep 2
done
echo "Database is ready."

# ✅ Apply database migrations
echo "Applying database migrations..."
conda run --no-capture-output -n myenv python manage.py migrate --noinput

# ✅ Collect static files
echo "Collecting static files..."
conda run --no-capture-output -n myenv python manage.py collectstatic --noinput

# ✅ Start Celery worker (background process)
echo "Starting Celery worker..."
conda run --no-capture-output -n myenv celery -A MechanicSetu worker --loglevel=info &

# ✅ Start Celery beat (optional - scheduler for periodic tasks)
echo "Starting Celery beat..."
conda run --no-capture-output -n myenv celery -A MechanicSetu beat --loglevel=info &

# ✅ Start Daphne (ASGI Server) on port 8000 for both HTTP + WebSocket
echo "Starting Daphne (ASGI - WebSocket + HTTP)..."
exec conda run --no-capture-output -n myenv daphne -b 0.0.0.0 -p 8000 MechanicSetu.asgi:application

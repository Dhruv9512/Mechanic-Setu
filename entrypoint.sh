#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# ✅ Print the environment variable to the log for debugging
echo "--- CHECKING ENVIRONMENT VARIABLE ---"
if [ -z "$BREVO_API_KEY" ]; then
  echo "BREVO_API_KEY is UNSET or EMPTY in the shell."
else
  echo "BREVO_API_KEY is SET in the shell."
fi
echo "-----------------------------------"

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

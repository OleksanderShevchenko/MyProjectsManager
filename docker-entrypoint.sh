#!/bin/sh
set -e

# Apply database migrations on startup if enabled (default: true)
if [ "${AUTO_MIGRATE:-true}" = "true" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

# Hand over to CMD
exec "$@"

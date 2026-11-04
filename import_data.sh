#!/bin/sh
set -e

echo "=== 1. Copying cleaned fixture into web container ==="
docker compose cp db_backups/clean_data.json web:/app/clean_data.json

echo "=== 2. Loading data into PostgreSQL ==="
docker compose exec -T web python manage.py loaddata clean_data.json

echo "=== 3. Cleaning up temporary file in container ==="
docker compose exec -T web rm -f /app/clean_data.json

echo "=== SUCCESS: Data import completed successfully! ==="

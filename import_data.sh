#!/bin/sh
set -e

echo "=== 1. Flushing existing empty data ==="
docker compose exec -T web python manage.py flush --no-input

echo "=== 2. Copying cleaned fixture into web container ==="
docker compose cp db_backups/clean_data.json web:/app/clean_data.json

echo "=== 3. Loading data into PostgreSQL ==="
docker compose exec -T web python manage.py loaddata clean_data.json

echo "=== 3. Cleaning up temporary file in container ==="
docker compose exec -T web rm -f /app/clean_data.json

echo "=== SUCCESS: Data import completed successfully! ==="

#!/bin/bash
set -e

if [ "$1" = "migrate" ]
then
    # Migrations
    uv run alembic upgrade head
elif  [ -n "$1" ]; then
    exec "$@"
fi

if [ $# -eq 0 ]
then
    OPTIONS=""
    if [ "$ENV" = "development" ] ; then
        uv run python -u src/config/db_health_check.py
        OPTIONS="--reload"
    fi
    uv run uvicorn src.main:app --host 0.0.0.0 $OPTIONS
fi

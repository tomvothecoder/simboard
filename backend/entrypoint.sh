#!/usr/bin/env sh
set -e

MODE="${1:-serve}"

require_database_url() {
    if [ -z "${DATABASE_URL}" ]; then
        echo "error: DATABASE_URL is required but not set"
        exit 1
    fi
}

normalize_pg_url() {
    db_url="$1"
    case "${db_url}" in
        postgresql+*://*)
            echo "postgresql://${db_url#*://}"
            ;;
        *)
            echo "${db_url}"
            ;;
    esac
}

wait_for_database() {
    pg_url="$(normalize_pg_url "${DATABASE_URL}")"
    retries=0
    max_retries="${DB_READY_MAX_RETRIES:-30}"
    retry_sleep_seconds="${DB_READY_RETRY_INTERVAL_SECONDS:-1}"

    echo "db readiness: waiting for postgres"
    until pg_isready -d "${pg_url}" -q; do
        retries=$((retries + 1))
        if [ "${retries}" -ge "${max_retries}" ]; then
            echo "db readiness: failed after ${max_retries} attempts"
            exit 1
        fi
        sleep "${retry_sleep_seconds}"
    done
    echo "db readiness: postgres is ready"
}

start_server() {
    if [ "${ENV}" = "production" ]; then
        echo "serve: starting backend in production mode"
        # In production, HTTPS is expected to be handled by a reverse proxy.
        exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
    fi

    echo "serve: starting backend in development mode"
    if [ -z "${SSL_KEYFILE}" ] || [ -z "${SSL_CERTFILE}" ]; then
        echo "error: SSL_KEYFILE and SSL_CERTFILE are required in development mode"
        exit 1
    fi

    exec uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --ssl-keyfile "${SSL_KEYFILE}" \
        --ssl-certfile "${SSL_CERTFILE}" \
        --reload
}

run_migrations() {
    echo "migrate: starting migration workflow"
    require_database_url
    wait_for_database
    uv run python -m app.scripts.db.run_migrations
}

case "${MODE}" in
    serve)
        start_server
        ;;
    migrate)
        run_migrations
        ;;
    *)
        echo "error: unknown mode '${MODE}'. expected 'serve' or 'migrate'"
        exit 2
        ;;
esac

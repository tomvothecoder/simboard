#!/usr/bin/env sh
set -e

MODE="${1:-serve}"

start_server() {
    if [ "${ENV}" = "production" ]; then
        echo "serve: starting backend in production mode"
        # In production, HTTPS is expected to be handled by a reverse proxy.
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    fi

    echo "serve: starting backend in development mode"
    if [ -z "${SSL_KEYFILE}" ] || [ -z "${SSL_CERTFILE}" ]; then
        echo "error: SSL_KEYFILE and SSL_CERTFILE are required in development mode"
        exit 1
    fi

    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --ssl-keyfile "${SSL_KEYFILE}" \
        --ssl-certfile "${SSL_CERTFILE}" \
        --reload
}

case "${MODE}" in
    serve)
        start_server
        ;;
    *)
        echo "error: unknown mode '${MODE}'. expected 'serve'"
        exit 2
        ;;
esac

# NERSC Spin Workloads (Backend Migrations First)

This document defines the backend rollout order for NERSC Spin with a dedicated migrations workload, plus baseline frontend, database, and ingress workload configuration.
This runbook uses the Rancher UI as the primary deployment workflow.

## Rancher UI Configs

Configure these workloads in Rancher to match:

- [`deploy/spin/backend-workloads.yaml`](../../deploy/spin/backend-workloads.yaml)
- [`deploy/spin/backend-migrate-job.yaml`](../../deploy/spin/backend-migrate-job.yaml)
- [`deploy/spin/frontend-workloads.yaml`](../../deploy/spin/frontend-workloads.yaml)
- [`deploy/spin/db-workloads.yaml`](../../deploy/spin/db-workloads.yaml)
- [`deploy/spin/lb-workloads.yaml`](../../deploy/spin/lb-workloads.yaml)

### Backend Deployment (`backend`)

| Rancher field | Value |
|---|---|
| Workload type | `Deployment` |
| Name | `backend` |
| Labels | `app=simboard-backend` |
| Replicas | `1` |
| Container name | `backend` |
| Image | `registry.nersc.gov/e3sm/simboard/backend:<tag>` |
| Pull policy | `Always` |
| Image pull secret | `registry-nersc` |
| Command | leave empty (use image entrypoint) |
| Arguments | `serve` |
| Port | `8000/TCP` |
| Environment variable | `ENV=production`, `ENVIRONMENT=production`, `PORT=8000` |
| Environment variable from secret | `FRONTEND_ORIGIN` from secret `simboard-backend-runtime`, key `frontend_origin` |
| Environment variable from secret | `FRONTEND_AUTH_REDIRECT_URL` from secret `simboard-backend-runtime`, key `frontend_auth_redirect_url` |
| Environment variable from secret | `FRONTEND_ORIGINS` from secret `simboard-backend-runtime`, key `frontend_origins` |
| Environment variable from secret | `DATABASE_URL` from secret `simboard-backend-db`, key `app_database_url` |
| Environment variable from secret | `TEST_DATABASE_URL` from secret `simboard-backend-db`, key `test_database_url` |
| Environment variable from secret | `GITHUB_CLIENT_ID` from secret `simboard-backend-oauth`, key `client_id` |
| Environment variable from secret | `GITHUB_CLIENT_SECRET` from secret `simboard-backend-oauth`, key `client_secret` |
| Environment variable from secret | `GITHUB_REDIRECT_URL` from secret `simboard-backend-oauth`, key `redirect_url` |
| Environment variable from secret | `GITHUB_STATE_SECRET_KEY` from secret `simboard-backend-oauth`, key `state_secret_key` |
| Environment variable | `COOKIE_NAME=simboard_auth`, `COOKIE_SECURE=true`, `COOKIE_HTTPONLY=true`, `COOKIE_SAMESITE=none`, `COOKIE_MAX_AGE=3600` |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `DAC_OVERRIDE,NET_BIND_SERVICE`, drop `ALL` |

### Backend Service (`backend`)

| Rancher field | Value |
|---|---|
| Service type | `ClusterIP` |
| Service name | `backend` |
| Service selector label | `app=simboard-backend` |
| Service port | `8000/TCP` (target `8000`) |

### Migration Job (`simboard-backend-migrate`)

| Rancher field | Value |
|---|---|
| Workload type | `Job` |
| Name | `simboard-backend-migrate` |
| Labels | `app=simboard-backend-migrate` |
| Backoff limit | `0` |
| TTL seconds after finished | `3600` |
| Restart policy | `Never` |
| Container name | `migrate` |
| Image | `registry.nersc.gov/e3sm/simboard/backend:<tag>` |
| Pull policy | `Always` |
| Command | leave empty (use image entrypoint) |
| Arguments | `migrate` |
| Environment variable from secret | `DATABASE_URL` from secret `simboard-backend-db`, key `migration_database_url` |
| Environment variable | `MIGRATION_LOCK_TIMEOUT_SECONDS=300` |
| Optional environment variable | `MIGRATION_LOCK_KEY=<integer lock key>` |

Reusable per-tag template: [`deploy/spin/backend-migrate-job.yaml`](../../deploy/spin/backend-migrate-job.yaml) (set `backend:<tag>` before running).

Use the same backend image tag in both workloads during rollout.

### Frontend Deployment (`frontend`)

| Rancher field | Value |
|---|---|
| Workload type | `Deployment` |
| Name | `frontend` |
| Labels | `app=simboard-frontend` |
| Replicas | `1` |
| Container name | `frontend` |
| Image | `registry.nersc.gov/e3sm/simboard/frontend:<tag>` |
| Pull policy | `Always` for `:dev`; `IfNotPresent` for versioned tags |
| Command | leave empty (use image CMD) |
| Arguments | leave empty |
| Port | `80/TCP` |
| Image pull secret | `registry-nersc` |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `CHOWN,SETGID,SETUID,NET_BIND_SERVICE`, drop `ALL` |

### Frontend Service (`frontend`)

| Rancher field | Value |
|---|---|
| Service type | `ClusterIP` |
| Service name | `frontend` |
| Service selector label | `app=simboard-frontend` |
| Service port | `80/TCP` (target `80`) |

### DB Service (`db`)

| Rancher field | Value |
|---|---|
| Service type | `ClusterIP` |
| Service name | `db` |
| Service selector label | `app=simboard-db` |
| Service port | `5432/TCP` (target `5432`) |

### DB Deployment (`db`)

| Rancher field | Value |
|---|---|
| Workload type | `Deployment` |
| Name | `db` |
| Labels | `app=simboard-db` |
| Replicas | `1` |
| Container name | `db` |
| Image | `postgres:17` |
| Pull policy | `Always` |
| Port | `5432/TCP` |
| Environment variable from secret | `POSTGRES_USER` from secret `simboard-db`, key `postgres_user` |
| Environment variable from secret | `POSTGRES_PASSWORD` from secret `simboard-db`, key `postgres_password` |
| Environment variable | `POSTGRES_DB=simboard` |
| Environment variable | `POSTGRES_PORT=5432` |
| Environment variable | `POSTGRES_SERVER=db` |
| Environment variable | `PGDATA=/var/lib/postgresql/data/pgdata` |
| Environment variable | `PGTZ=America/Los_Angeles` |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID`, drop `ALL` |

### TLS Secret (`simboard-tls-cert`)

| Rancher field | Value |
|---|---|
| Resource type | `Secret` |
| Name | `simboard-tls-cert` |
| Secret type | `kubernetes.io/tls` |
| Data key | `tls.crt` (certificate PEM) |
| Data key | `tls.key` (private key PEM) |

### Ingress (`lb`)

| Rancher field | Value |
|---|---|
| Resource type | `Ingress` |
| Name | `lb` |
| Ingress class | `nginx` |
| TLS secret | `simboard-tls-cert` |
| TLS hosts | `simboard-dev.e3sm.org`, `simboard-dev-api.e3sm.org`, `lb.simboard.development.svc.spin.nersc.org` |
| Rule | Host `simboard-dev.e3sm.org`, path `/`, service `frontend:80` |
| Rule | Host `simboard-dev-api.e3sm.org`, path `/`, service `backend:8000` |
| Optional host alias | `lb.simboard.development.svc.spin.nersc.org` |

## Required Secrets

Create a Kubernetes secret (example: `simboard-backend-db`) with:

- `app_database_url`: app credential used by backend deployment
- `migration_database_url`: migration credential with schema-altering privileges
- `test_database_url`: backend test URL required by runtime settings

If separate DB users are not available yet, both keys can point to the same connection URL.

Create a backend runtime secret (example: `simboard-backend-runtime`) with:

- `frontend_origin`: primary frontend origin
- `frontend_auth_redirect_url`: frontend OAuth callback route
- `frontend_origins`: comma-separated CORS allow-list

Create a backend OAuth secret (example: `simboard-backend-oauth`) with:

- `client_id`: GitHub OAuth app client ID
- `client_secret`: GitHub OAuth app client secret
- `redirect_url`: backend OAuth callback URL
- `state_secret_key`: OAuth state signing secret

Create a DB credential secret (example: `simboard-db`) with:

- `postgres_user`: Postgres user for container bootstrap
- `postgres_password`: Postgres password for container bootstrap

Create a TLS secret (example: `simboard-tls-cert`) with:

- `tls.crt`: TLS certificate in PEM format
- `tls.key`: TLS private key in PEM format

## Deploy Order

1. Open the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home) and select the target namespace.
2. Ensure DB service/deployment (`db`) are healthy in **Service Discovery → Services** and **Workloads → Deployments**.
3. Navigate to **Workloads → Jobs** and open `simboard-backend-migrate`.
4. Ensure the job image uses the target backend tag, then run or recreate the job so that migration executes with that tag.
5. Wait for job status **Completed**.
6. Review migration logs from **⋮ → View Logs** on `simboard-backend-migrate`.
7. After migration success, navigate to **Workloads → Deployments**, open `backend`, and update/redeploy it with the same image tag.
8. Verify rollout success by confirming the deployment is healthy and pods are **Running** under **Workloads → Pods**.
9. Verify ingress routing under **Service Discovery → Ingresses** for `lb` and confirm both frontend and backend hosts resolve via HTTPS.

Frontend deploys independently from backend migrations. For frontend releases, update/redeploy the `frontend` deployment in **Workloads → Deployments** with the target frontend image tag.

## Failure Handling

- If migration job status is **Failed** or logs show errors, do not roll out backend with that image tag.
- Fix the migration issue and rerun the migration job in Rancher.
- Backend image rollback does not revert schema automatically; handle schema rollback explicitly via Alembic when required.

## Concurrency Behavior

Migration mode takes a Postgres advisory lock before running Alembic.

- Only one migration runner can hold the lock at a time, even if multiple job runs are triggered in Rancher.
- Waiting behavior is controlled by `MIGRATION_LOCK_TIMEOUT_SECONDS` (default `300`).
- Optional `MIGRATION_LOCK_KEY` can override the deterministic lock key.

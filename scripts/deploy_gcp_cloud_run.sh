#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
REGION="${REGION:-us-east1}"
REPOSITORY="${REPOSITORY:-gwx-gar-intern-01}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-gwx-sa-intern-01@${PROJECT_ID}.iam.gserviceaccount.com}"
VPC_CONNECTOR="${VPC_CONNECTOR:-gwx-vpc-conn-intern-01}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

CORE_SERVICE_NAME="${CORE_SERVICE_NAME:-cap-core-assessment-platform-service}"
EXECUTION_SERVICE_NAME="${EXECUTION_SERVICE_NAME:-cap-code-execution-service}"
EVALUATION_SERVICE_NAME="${EVALUATION_SERVICE_NAME:-cap-code-evaluation-service}"
GATEWAY_SERVICE_NAME="${GATEWAY_SERVICE_NAME:-cap-api-gateway-service}"
FRONTEND_SERVICE_NAME="${FRONTEND_SERVICE_NAME:-cap-frontend}"
EVALUATION_WORKER_POOL_NAME="${EVALUATION_WORKER_POOL_NAME:-cap-code-evaluation-worker}"

CORE_MIGRATION_JOB_NAME="${CORE_MIGRATION_JOB_NAME:-cap-core-assessment-platform-migrate}"
EVALUATION_MIGRATION_JOB_NAME="${EVALUATION_MIGRATION_JOB_NAME:-cap-code-evaluation-migrate}"

DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-gwx-cap-database-url}"
INTERNAL_TOKEN_SECRET="${INTERNAL_TOKEN_SECRET:-gwx-cap-internal-service-token}"
CANDIDATE_SECRET_SECRET="${CANDIDATE_SECRET_SECRET:-gwx-cap-candidate-session-secret}"
INVITE_PEPPER_SECRET="${INVITE_PEPPER_SECRET:-gwx-cap-invite-token-pepper}"
GROQ_API_KEY_SECRET="${GROQ_API_KEY_SECRET:-gwx-cap-groq-api-key}"
GROQ_API_KEY_1_SECRET="${GROQ_API_KEY_1_SECRET:-gwx-cap-groq-api-key-1}"
GROQ_API_KEY_2_SECRET="${GROQ_API_KEY_2_SECRET:-gwx-cap-groq-api-key-2}"
GROQ_API_KEY_3_SECRET="${GROQ_API_KEY_3_SECRET:-gwx-cap-groq-api-key-3}"
GROQ_API_KEY_4_SECRET="${GROQ_API_KEY_4_SECRET:-gwx-cap-groq-api-key-4}"
LANGSMITH_API_KEY_SECRET="${LANGSMITH_API_KEY_SECRET:-gwx-cap-langsmith-api-key}"
BREVO_API_KEY_SECRET="${BREVO_API_KEY_SECRET:-gwx-cap-brevo-api-key}"

DB_NAME="${DB_NAME:-cap_core}"
DB_USER="${DB_USER:-raghavs}"
DB_PORT="${DB_PORT:-5432}"
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-}"
REDIS_URL="${REDIS_URL:-}"
JUDGE0_BASE_URL="${JUDGE0_BASE_URL:-http://10.0.1.2:8080}"
DEPLOY_JUDGE0="${DEPLOY_JUDGE0:-true}"
JUDGE0_GCE_INSTANCE="${JUDGE0_GCE_INSTANCE:-gwx-gce-intern-01}"
JUDGE0_GCE_ZONE="${JUDGE0_GCE_ZONE:-us-east1-b}"

BOOTSTRAP_HTTPS_ORIGIN="${BOOTSTRAP_HTTPS_ORIGIN:-https://bootstrap.local}"
ARTIFACT_REGISTRY_HOST="${REGION}-docker.pkg.dev"
BUILD_MODE="${BUILD_MODE:-docker}"
SKIP_BACKEND_BUILDS="${SKIP_BACKEND_BUILDS:-false}"
DEPLOY_EVALUATION_WORKER="${DEPLOY_EVALUATION_WORKER:-true}"
EVALUATION_WORKER_INSTANCES="${EVALUATION_WORKER_INSTANCES:-1}"

usage() {
  cat <<USAGE
Deploy CAP services to Cloud Run.

Required before first run:
  gcloud auth login --login-config=/path/to/workforce-login-config.json

Required env vars unless already present in Secret Manager:
  CLOUDSQL_INSTANCE, DB_HOST, or DATABASE_URL
  DB_PASSWORD if DATABASE_URL is not set
  JUDGE0_BASE_URL (defaults to http://10.0.1.2:8080)

Useful optional env vars:
  DEPLOY_JUDGE0=true
  JUDGE0_GCE_INSTANCE
  JUDGE0_GCE_ZONE
  BUILD_MODE=cloudbuild|docker
  SKIP_BACKEND_BUILDS=true
  DEPLOY_EVALUATION_WORKER=false
  EVALUATION_WORKER_INSTANCES=1
  REDIS_URL
  FIREBASE_API_KEY
  FIREBASE_AUTH_DOMAIN
  FIREBASE_PROJECT_ID
  FIREBASE_APP_ID
  GROQ_API_KEY
  BREVO_API_KEY
  BREVO_SENDER_EMAIL

Examples:
  CLOUDSQL_INSTANCE='project:region:instance' DB_PASSWORD='...' \\
    JUDGE0_BASE_URL='https://judge0.example' \\
    scripts/deploy_gcp_cloud_run.sh

USAGE
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  command_exists "$1" || die "Missing required command: $1"
}

require_build_tools() {
  case "$BUILD_MODE" in
    cloudbuild)
      require_command gcloud
      ;;
    docker)
      require_command docker
      ;;
    *)
      die "BUILD_MODE must be cloudbuild or docker"
      ;;
  esac
}

secret_exists() {
  gcloud secrets describe "$1" \
    --project="$PROJECT_ID" \
    --format='value(name)' >/dev/null 2>&1
}

put_secret_value() {
  local name="$1"
  local value="$2"

  if secret_exists "$name"; then
    printf '%s' "$value" | gcloud secrets versions add "$name" \
      --project="$PROJECT_ID" \
      --data-file=- >/dev/null
  else
    printf '%s' "$value" | gcloud secrets create "$name" \
      --project="$PROJECT_ID" \
      --replication-policy=user-managed \
      --locations="$REGION" \
      --data-file=- >/dev/null
  fi
}

ensure_secret_value() {
  local name="$1"
  local value="${2:-}"
  local generator="${3:-}"

  if [[ -n "$value" ]]; then
    put_secret_value "$name" "$value"
    return
  fi

  if secret_exists "$name"; then
    return
  fi

  [[ -n "$generator" ]] || die "Secret $name does not exist and no value was provided"
  put_secret_value "$name" "$("$generator")"
}

random_secret() {
  openssl rand -base64 48
}

join_with_at_delimiter() {
  local output='^@^'
  local first=true
  local item

  for item in "$@"; do
    if [[ "$first" == true ]]; then
      output+="$item"
      first=false
    else
      output+="@$item"
    fi
  done

  printf '%s' "$output"
}

image_uri() {
  local service_name="$1"
  printf '%s/%s/%s/%s:%s' \
    "$ARTIFACT_REGISTRY_HOST" \
    "$PROJECT_ID" \
    "$REPOSITORY" \
    "$service_name" \
    "$IMAGE_TAG"
}

service_url() {
  local service_name="$1"
  gcloud run services describe "$service_name" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)'
}

build_and_push() {
  local service_name="$1"
  local service_dir="$2"
  local image
  image="$(image_uri "$service_name")"

  if [[ "$SKIP_BACKEND_BUILDS" == "true" ]]; then
    log "Skipping existing backend image $service_name"
    return
  fi

  if [[ "$BUILD_MODE" == "cloudbuild" ]]; then
    log "Building and pushing $service_name with Cloud Build"
    gcloud builds submit "$service_dir" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --default-buckets-behavior=regional-user-owned-bucket \
      --tag="$image"
    return
  fi

  log "Building and pushing $service_name for linux/amd64"
  docker buildx build \
    --platform=linux/amd64 \
    --provenance=false \
    --push \
    -t "$image" \
    "$service_dir"
}

deploy_http_service() {
  local service_name="$1"
  local image="$2"
  local port="$3"
  local env_vars="$4"
  local secret_vars="$5"
  shift 5

  local cloudsql_args=()
  if [[ -n "$CLOUDSQL_INSTANCE" ]]; then
    cloudsql_args+=(--add-cloudsql-instances="$CLOUDSQL_INSTANCE")
  fi

  log "Deploying $service_name"
  gcloud run deploy "$service_name" \
    --image="$image" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --platform=managed \
    --allow-unauthenticated \
    --port="$port" \
    --cpu=1 \
    --memory=512Mi \
    --min-instances=0 \
    --max-instances=2 \
    --min=0 \
    --max=2 \
    --service-account="$SERVICE_ACCOUNT" \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=private-ranges-only \
    --set-env-vars="$env_vars" \
    --set-secrets="$secret_vars" \
    "${cloudsql_args[@]}" \
    "$@"
}

deploy_migration_job() {
  local job_name="$1"
  local image="$2"
  local env_vars="$3"
  local secret_vars="$4"

  local cloudsql_args=()
  if [[ -n "$CLOUDSQL_INSTANCE" ]]; then
    cloudsql_args+=(--set-cloudsql-instances="$CLOUDSQL_INSTANCE")
  fi

  log "Deploying migration job $job_name"
  gcloud run jobs deploy "$job_name" \
    --image="$image" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$SERVICE_ACCOUNT" \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=private-ranges-only \
    --command=alembic \
    --args=-c,alembic.ini,upgrade,head \
    --set-env-vars="$env_vars" \
    --set-secrets="$secret_vars" \
    "${cloudsql_args[@]}"

  log "Running migration job $job_name"
  gcloud run jobs execute "$job_name" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --wait
}

deploy_worker_pool() {
  local pool_name="$1"
  local image="$2"
  local env_vars="$3"
  local secret_vars="$4"

  local cloudsql_args=()
  if [[ -n "$CLOUDSQL_INSTANCE" ]]; then
    cloudsql_args+=(--set-cloudsql-instances="$CLOUDSQL_INSTANCE")
  fi

  log "Deploying worker pool $pool_name"
  gcloud run worker-pools deploy "$pool_name" \
    --image="$image" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$SERVICE_ACCOUNT" \
    --instances="$EVALUATION_WORKER_INSTANCES" \
    --cpu=1 \
    --memory=512Mi \
    --command=python \
    --args=-m,worker \
    --set-env-vars="$env_vars" \
    --set-secrets="$secret_vars" \
    "${cloudsql_args[@]}"
}

frontend_build() {
  local gateway_url="$1"
  local image
  image="$(image_uri "$FRONTEND_SERVICE_NAME")"

  if [[ "$BUILD_MODE" == "cloudbuild" ]]; then
    local build_config
    build_config="$(mktemp "${TMPDIR:-/tmp}/cap-frontend-cloudbuild.XXXXXX.yaml")"

    cat >"$build_config" <<'YAML'
steps:
  - name: gcr.io/cloud-builders/docker
    env:
      - DOCKER_BUILDKIT=1
    args:
      - build
      - --build-arg
      - VITE_API_GATEWAY_BASE_URL=${_VITE_API_GATEWAY_BASE_URL}
      - --build-arg
      - VITE_FIREBASE_API_KEY=${_VITE_FIREBASE_API_KEY}
      - --build-arg
      - VITE_FIREBASE_AUTH_DOMAIN=${_VITE_FIREBASE_AUTH_DOMAIN}
      - --build-arg
      - VITE_FIREBASE_PROJECT_ID=${_VITE_FIREBASE_PROJECT_ID}
      - --build-arg
      - VITE_FIREBASE_APP_ID=${_VITE_FIREBASE_APP_ID}
      - -t
      - ${_IMAGE}
      - .
images:
  - ${_IMAGE}
YAML

    log "Building and pushing frontend with Cloud Build and gateway URL $gateway_url"
    if ! gcloud builds submit frontend \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --default-buckets-behavior=regional-user-owned-bucket \
      --config="$build_config" \
      --substitutions="$(join_with_at_delimiter \
        _IMAGE="$image" \
        _VITE_API_GATEWAY_BASE_URL="/api/v1" \
        _VITE_FIREBASE_API_KEY="${FIREBASE_API_KEY:-${VITE_FIREBASE_API_KEY:-}}" \
        _VITE_FIREBASE_AUTH_DOMAIN="${FIREBASE_AUTH_DOMAIN:-${VITE_FIREBASE_AUTH_DOMAIN:-}}" \
        _VITE_FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-${VITE_FIREBASE_PROJECT_ID:-}}" \
        _VITE_FIREBASE_APP_ID="${FIREBASE_APP_ID:-${VITE_FIREBASE_APP_ID:-}}")"; then
      rm -f "$build_config"
      return 1
    fi
    rm -f "$build_config"
    return
  fi

  log "Building frontend for nginx same-origin proxy (/api/v1)"
  local firebase_api_key firebase_auth_domain firebase_project_id firebase_app_id
  firebase_api_key="$(firebase_build_arg VITE_FIREBASE_API_KEY)"
  firebase_auth_domain="$(firebase_build_arg VITE_FIREBASE_AUTH_DOMAIN)"
  firebase_project_id="$(firebase_build_arg VITE_FIREBASE_PROJECT_ID)"
  firebase_app_id="$(firebase_build_arg VITE_FIREBASE_APP_ID)"

  local docker_build_args=(
    --platform=linux/amd64
    --provenance=false
    --push
    --build-arg "VITE_API_GATEWAY_BASE_URL=/api/v1"
    --build-arg "VITE_FIREBASE_API_KEY=${firebase_api_key}"
    --build-arg "VITE_FIREBASE_AUTH_DOMAIN=${firebase_auth_domain}"
    --build-arg "VITE_FIREBASE_PROJECT_ID=${firebase_project_id}"
    --build-arg "VITE_FIREBASE_APP_ID=${firebase_app_id}"
    -t "$image"
    frontend
  )

  if [[ -f frontend/.env ]]; then
    docker buildx build \
      "${docker_build_args[@]}" \
      --secret id=frontend_env,src=frontend/.env
  else
    docker buildx build "${docker_build_args[@]}"
  fi
}

maybe_add_secret_mapping() {
  local env_name="$1"
  local secret_name="$2"

  if secret_exists "$secret_name"; then
    printf ',%s=%s:latest' "$env_name" "$secret_name"
  fi
}

read_core_env_var() {
  local key="$1"
  local file="core-assessment-platform-service/.env"

  [[ -f "$file" ]] || return 0
  python3 - "$key" "$file" <<'PY'
import sys

key, path = sys.argv[1], sys.argv[2]
for line in open(path, encoding="utf-8"):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    name, value = stripped.split("=", 1)
    if name.strip() == key:
        print(value.strip().strip('"').strip("'"))
        break
PY
}

read_frontend_env_var() {
  local key="$1"
  local file="frontend/.env"

  [[ -f "$file" ]] || return 0
  python3 - "$key" "$file" <<'PY'
import sys

key, path = sys.argv[1], sys.argv[2]
for line in open(path, encoding="utf-8"):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    name, value = stripped.split("=", 1)
    if name.strip() == key:
        print(value.strip().strip('"').strip("'"))
        break
PY
}

firebase_build_arg() {
  local vite_key="$1"
  local value=""

  case "$vite_key" in
    VITE_FIREBASE_API_KEY) value="${FIREBASE_API_KEY:-${VITE_FIREBASE_API_KEY:-}}" ;;
    VITE_FIREBASE_AUTH_DOMAIN) value="${FIREBASE_AUTH_DOMAIN:-${VITE_FIREBASE_AUTH_DOMAIN:-}}" ;;
    VITE_FIREBASE_PROJECT_ID) value="${FIREBASE_PROJECT_ID:-${VITE_FIREBASE_PROJECT_ID:-}}" ;;
    VITE_FIREBASE_APP_ID) value="${FIREBASE_APP_ID:-${VITE_FIREBASE_APP_ID:-}}" ;;
  esac

  if [[ -z "$value" ]]; then
    value="$(read_frontend_env_var "$vite_key")"
  fi

  printf '%s' "$value"
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  require_command gcloud
  require_command openssl
  require_build_tools

  gcloud config set project "$PROJECT_ID" >/dev/null
  if [[ "$BUILD_MODE" == "docker" ]]; then
    gcloud auth configure-docker "$ARTIFACT_REGISTRY_HOST" --quiet
  fi

  if [[ -z "${DATABASE_URL:-}" ]]; then
    if [[ -n "${DB_PASSWORD:-}" ]] || ! secret_exists "$DATABASE_URL_SECRET"; then
      if [[ -z "${DB_PASSWORD:-}" ]]; then
        read -rsp "Postgres password for ${DB_USER}: " DB_PASSWORD
        printf '\n'
      fi
      if [[ -n "$CLOUDSQL_INSTANCE" ]]; then
        DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CLOUDSQL_INSTANCE}"
      else
        [[ -n "${DB_HOST:-}" ]] || die "Set CLOUDSQL_INSTANCE, DB_HOST, or DATABASE_URL before running"
        DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
      fi
    fi
  fi

  if [[ "$DEPLOY_JUDGE0" == "true" ]]; then
    log "Deploying Judge0 to ${JUDGE0_GCE_INSTANCE}"
    JUDGE0_BASE_URL="$JUDGE0_BASE_URL" \
      JUDGE0_GCE_INSTANCE="$JUDGE0_GCE_INSTANCE" \
      JUDGE0_GCE_ZONE="$JUDGE0_GCE_ZONE" \
      BUILD_MODE="$BUILD_MODE" \
      PROJECT_ID="$PROJECT_ID" \
      REGION="$REGION" \
      REPOSITORY="$REPOSITORY" \
      IMAGE_TAG="$IMAGE_TAG" \
      DATABASE_URL_SECRET="$DATABASE_URL_SECRET" \
      DB_USER="$DB_USER" \
      DB_PASSWORD="${DB_PASSWORD:-}" \
      "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy_gcp_judge0.sh"
  fi

  log "Preparing Secret Manager values"
  ensure_secret_value "$DATABASE_URL_SECRET" "${DATABASE_URL:-}"
  ensure_secret_value "$INTERNAL_TOKEN_SECRET" "${INTERNAL_SERVICE_TOKEN:-}" random_secret
  ensure_secret_value "$CANDIDATE_SECRET_SECRET" "${CANDIDATE_SESSION_SECRET:-}" random_secret
  ensure_secret_value "$INVITE_PEPPER_SECRET" "${INVITE_TOKEN_PEPPER:-}" random_secret
  if [[ -n "${GROQ_API_KEY:-}" ]]; then
    ensure_secret_value "$GROQ_API_KEY_SECRET" "$GROQ_API_KEY"
  fi
  local groq_slot groq_slot_secret groq_slot_value
  for groq_slot in 1 2 3 4; do
    groq_slot_secret="GROQ_API_KEY_${groq_slot}_SECRET"
    groq_slot_value="${!groq_slot_secret}"
    local env_var="GROQ_API_KEY_${groq_slot}"
    local resolved="${!env_var:-}"
    if [[ -z "$resolved" ]]; then
      resolved="$(read_core_env_var "$env_var")"
    fi
    if [[ -n "$resolved" ]]; then
      ensure_secret_value "$groq_slot_value" "$resolved"
    fi
  done
  local langsmith_key="${LANGSMITH_API_KEY:-$(read_core_env_var LANGSMITH_API_KEY)}"
  if [[ -n "$langsmith_key" ]]; then
    ensure_secret_value "$LANGSMITH_API_KEY_SECRET" "$langsmith_key"
  fi
  if [[ -n "${BREVO_API_KEY:-}" ]]; then
    ensure_secret_value "$BREVO_API_KEY_SECRET" "$BREVO_API_KEY"
  fi

  local common_backend_env
  common_backend_env="$(join_with_at_delimiter \
    APP_ENV=production \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    API_PREFIX=/api/v1 \
    CORS_ALLOWED_ORIGINS="$BOOTSTRAP_HTTPS_ORIGIN")"

  local common_backend_secrets
  common_backend_secrets="INTERNAL_SERVICE_TOKEN=${INTERNAL_TOKEN_SECRET}:latest"

  build_and_push "$EXECUTION_SERVICE_NAME" code-execution-service
  build_and_push "$EVALUATION_SERVICE_NAME" code-evaluation-service
  build_and_push "$CORE_SERVICE_NAME" core-assessment-platform-service
  build_and_push "$GATEWAY_SERVICE_NAME" api-gateway-service

  local execution_image evaluation_image core_image gateway_image frontend_image
  execution_image="$(image_uri "$EXECUTION_SERVICE_NAME")"
  evaluation_image="$(image_uri "$EVALUATION_SERVICE_NAME")"
  core_image="$(image_uri "$CORE_SERVICE_NAME")"
  gateway_image="$(image_uri "$GATEWAY_SERVICE_NAME")"
  frontend_image="$(image_uri "$FRONTEND_SERVICE_NAME")"

  local execution_env
  execution_env="$(join_with_at_delimiter \
    APP_ENV=production \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    API_PREFIX=/api/v1 \
    CORS_ALLOWED_ORIGINS="$BOOTSTRAP_HTTPS_ORIGIN" \
    JUDGE0_BASE_URL="$JUDGE0_BASE_URL" \
    JUDGE0_AUTH_HEADER="${JUDGE0_AUTH_HEADER:-X-Auth-Token}" \
    JUDGE0_REQUEST_TIMEOUT_SECONDS="${JUDGE0_REQUEST_TIMEOUT_SECONDS:-10}" \
    JUDGE0_POLL_INTERVAL_SECONDS="${JUDGE0_POLL_INTERVAL_SECONDS:-0.5}" \
    JUDGE0_MAX_POLL_ATTEMPTS="${JUDGE0_MAX_POLL_ATTEMPTS:-30}" \
    DEFAULT_CPU_TIME_LIMIT_SECONDS="${DEFAULT_CPU_TIME_LIMIT_SECONDS:-2}" \
    DEFAULT_MEMORY_LIMIT_KB="${DEFAULT_MEMORY_LIMIT_KB:-128000}")"
  deploy_http_service "$EXECUTION_SERVICE_NAME" "$execution_image" 8000 "$execution_env" "$common_backend_secrets"
  local execution_url
  execution_url="$(service_url "$EXECUTION_SERVICE_NAME")"

  local evaluation_env evaluation_secrets
  evaluation_env="$(join_with_at_delimiter \
    APP_ENV=production \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    API_PREFIX=/api/v1 \
    CORS_ALLOWED_ORIGINS="$BOOTSTRAP_HTTPS_ORIGIN" \
    EVALUATION_REPORT_DIR=/app/data/reports \
    EVALUATION_DB_SCHEMA="${EVALUATION_DB_SCHEMA:-public}" \
    SEED_DEMO_EVALUATIONS=false \
    EVALUATION_WORKER_BATCH_SIZE="${EVALUATION_WORKER_BATCH_SIZE:-20}" \
    EVALUATION_WORKER_POLL_INTERVAL_SECONDS="${EVALUATION_WORKER_POLL_INTERVAL_SECONDS:-5}" \
    EVALUATION_RETENTION_DAYS="${EVALUATION_RETENTION_DAYS:-365}" \
    EVALUATION_JOB_LEASE_SECONDS="${EVALUATION_JOB_LEASE_SECONDS:-300}" \
    GROQ_BASE_URL="${GROQ_BASE_URL:-https://api.groq.com/openai/v1}" \
    GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}" \
    GROQ_REQUEST_TIMEOUT_SECONDS="${GROQ_REQUEST_TIMEOUT_SECONDS:-60}" \
    GROQ_RETRY_COUNT="${GROQ_RETRY_COUNT:-3}" \
    GROQ_MAX_SOURCE_CHARS="${GROQ_MAX_SOURCE_CHARS:-80000}")"
  evaluation_secrets="INTERNAL_SERVICE_TOKEN=${INTERNAL_TOKEN_SECRET}:latest,DATABASE_URL=${DATABASE_URL_SECRET}:latest"
  evaluation_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY "$GROQ_API_KEY_SECRET")"

  deploy_migration_job "$EVALUATION_MIGRATION_JOB_NAME" "$evaluation_image" "$evaluation_env" "$evaluation_secrets"
  deploy_http_service "$EVALUATION_SERVICE_NAME" "$evaluation_image" 8000 "$evaluation_env" "$evaluation_secrets"
  local evaluation_url
  evaluation_url="$(service_url "$EVALUATION_SERVICE_NAME")"

  if [[ "$DEPLOY_EVALUATION_WORKER" == "true" ]]; then
    deploy_worker_pool "$EVALUATION_WORKER_POOL_NAME" "$evaluation_image" "$evaluation_env" "$evaluation_secrets"
  fi

  local firebase_api_key firebase_auth_domain firebase_project_id firebase_app_id
  firebase_api_key="$(firebase_build_arg VITE_FIREBASE_API_KEY)"
  firebase_auth_domain="$(firebase_build_arg VITE_FIREBASE_AUTH_DOMAIN)"
  firebase_project_id="$(firebase_build_arg VITE_FIREBASE_PROJECT_ID)"
  firebase_app_id="$(firebase_build_arg VITE_FIREBASE_APP_ID)"

  local core_env core_secrets
  core_env="$(join_with_at_delimiter \
    APP_ENV=production \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    API_PREFIX=/api/v1 \
    CORS_ALLOWED_ORIGINS="$BOOTSTRAP_HTTPS_ORIGIN" \
    APP_BASE_URL="$BOOTSTRAP_HTTPS_ORIGIN" \
    REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}" \
    CODE_EXECUTION_API_BASE_URL="${execution_url}/api/v1" \
    CODE_EXECUTION_REQUEST_TIMEOUT_SECONDS="${CODE_EXECUTION_REQUEST_TIMEOUT_SECONDS:-300}" \
    CODE_EVALUATION_API_BASE_URL="${evaluation_url}/api/v1" \
    CODE_EVALUATION_REQUEST_TIMEOUT_SECONDS="${CODE_EVALUATION_REQUEST_TIMEOUT_SECONDS:-30}" \
    AUTO_CREATE_RECRUITER_ROLE="${AUTO_CREATE_RECRUITER_ROLE:-true}" \
    FIREBASE_API_KEY="$firebase_api_key" \
    FIREBASE_AUTH_DOMAIN="$firebase_auth_domain" \
    FIREBASE_PROJECT_ID="$firebase_project_id" \
    FIREBASE_APP_ID="$firebase_app_id" \
    GROQ_BASE_URL="${GROQ_BASE_URL:-https://api.groq.com/openai/v1}" \
    GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}" \
    GROQ_GPT_OSS_MODEL="${GROQ_GPT_OSS_MODEL:-openai/gpt-oss-120b}" \
    GROQ_RETRY_COUNT="${GROQ_RETRY_COUNT:-3}" \
    GROQ_RETRY_BACKOFF_SECONDS="${GROQ_RETRY_BACKOFF_SECONDS:-0.5}" \
    GROQ_REQUEST_TIMEOUT_SECONDS="${GROQ_REQUEST_TIMEOUT_SECONDS:-60}" \
    LANGSMITH_TRACING="${LANGSMITH_TRACING:-true}" \
    LANGSMITH_ENDPOINT="${LANGSMITH_ENDPOINT:-https://api.smith.langchain.com}" \
    LANGSMITH_PROJECT="${LANGSMITH_PROJECT:-CAP}" \
    BREVO_BASE_URL="${BREVO_BASE_URL:-https://api.brevo.com/v3}" \
    BREVO_SENDER_EMAIL="${BREVO_SENDER_EMAIL:-}" \
    BREVO_SENDER_NAME="${BREVO_SENDER_NAME:-CAP Assessments}" \
    BREVO_REQUEST_TIMEOUT_SECONDS="${BREVO_REQUEST_TIMEOUT_SECONDS:-30}")"
  core_secrets="DATABASE_URL=${DATABASE_URL_SECRET}:latest,INTERNAL_SERVICE_TOKEN=${INTERNAL_TOKEN_SECRET}:latest,INVITE_TOKEN_PEPPER=${INVITE_PEPPER_SECRET}:latest,CANDIDATE_SESSION_SECRET=${CANDIDATE_SECRET_SECRET}:latest"
  core_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY "$GROQ_API_KEY_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY_1 "$GROQ_API_KEY_1_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY_2 "$GROQ_API_KEY_2_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY_3 "$GROQ_API_KEY_3_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping GROQ_API_KEY_4 "$GROQ_API_KEY_4_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping LANGSMITH_API_KEY "$LANGSMITH_API_KEY_SECRET")"
  core_secrets+="$(maybe_add_secret_mapping BREVO_API_KEY "$BREVO_API_KEY_SECRET")"

  deploy_migration_job "$CORE_MIGRATION_JOB_NAME" "$core_image" "$core_env" "$core_secrets"
  deploy_http_service "$CORE_SERVICE_NAME" "$core_image" 8000 "$core_env" "$core_secrets"
  local core_url
  core_url="$(service_url "$CORE_SERVICE_NAME")"

  local gateway_env gateway_secrets
  gateway_env="$(join_with_at_delimiter \
    APP_ENV=production \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    API_PREFIX=/api/v1 \
    CORS_ALLOWED_ORIGINS="$BOOTSTRAP_HTTPS_ORIGIN" \
    CORE_SERVICE_BASE_URL="$core_url" \
    CODE_EXECUTION_SERVICE_BASE_URL="$execution_url" \
    CODE_EVALUATION_SERVICE_BASE_URL="$evaluation_url" \
    UPSTREAM_REQUEST_TIMEOUT_SECONDS="${UPSTREAM_REQUEST_TIMEOUT_SECONDS:-120}" \
    FIREBASE_API_KEY="$firebase_api_key" \
    FIREBASE_AUTH_DOMAIN="$firebase_auth_domain" \
    FIREBASE_PROJECT_ID="$firebase_project_id" \
    FIREBASE_APP_ID="$firebase_app_id")"
  gateway_secrets="INTERNAL_SERVICE_TOKEN=${INTERNAL_TOKEN_SECRET}:latest,CANDIDATE_SESSION_SECRET=${CANDIDATE_SECRET_SECRET}:latest"
  deploy_http_service "$GATEWAY_SERVICE_NAME" "$gateway_image" 8000 "$gateway_env" "$gateway_secrets"
  local gateway_url
  gateway_url="$(service_url "$GATEWAY_SERVICE_NAME")"

  frontend_build "$gateway_url"
  deploy_http_service "$FRONTEND_SERVICE_NAME" "$frontend_image" 80 \
    "$(join_with_at_delimiter \
      NODE_ENV=production \
      API_GATEWAY_PROXY_URL="${gateway_url}/api/v1")" \
    "INTERNAL_SERVICE_TOKEN=${INTERNAL_TOKEN_SECRET}:latest"
  local frontend_url
  frontend_url="$(service_url "$FRONTEND_SERVICE_NAME")"

  local final_cors
  final_cors="${CORS_ALLOWED_ORIGINS:-$frontend_url,$gateway_url}"

  log "Updating final CORS and app URLs"
  gcloud run services update "$CORE_SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --update-env-vars="$(join_with_at_delimiter CORS_ALLOWED_ORIGINS="$final_cors" APP_BASE_URL="$frontend_url")"

  gcloud run services update "$GATEWAY_SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --update-env-vars="$(join_with_at_delimiter CORS_ALLOWED_ORIGINS="$final_cors")"

  gcloud run services update "$EXECUTION_SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --update-env-vars="$(join_with_at_delimiter CORS_ALLOWED_ORIGINS="$final_cors")"

  gcloud run services update "$EVALUATION_SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --update-env-vars="$(join_with_at_delimiter CORS_ALLOWED_ORIGINS="$final_cors")"

  log "Deployment complete"
  printf 'Frontend: %s\n' "$frontend_url"
  printf 'Gateway:  %s\n' "$gateway_url"
  printf 'Core:     %s\n' "$core_url"
  printf 'Execution:%s\n' "$execution_url"
  printf 'Evaluation:%s\n' "$evaluation_url"
  if [[ "$DEPLOY_EVALUATION_WORKER" == "true" ]]; then
    printf 'Evaluation worker pool: %s\n' "$EVALUATION_WORKER_POOL_NAME"
  fi
}

main "$@"

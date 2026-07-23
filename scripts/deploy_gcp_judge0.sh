#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
REGION="${REGION:-us-east1}"
REPOSITORY="${REPOSITORY:-gwx-gar-intern-01}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ARTIFACT_REGISTRY_HOST="${REGION}-docker.pkg.dev"

JUDGE0_IMAGE_NAME="${JUDGE0_IMAGE_NAME:-cap-judge0-slim}"
JUDGE0_GCE_INSTANCE="${JUDGE0_GCE_INSTANCE:-gwx-gce-intern-01}"
JUDGE0_GCE_ZONE="${JUDGE0_GCE_ZONE:-us-east1-b}"
JUDGE0_LISTEN_PORT="${JUDGE0_LISTEN_PORT:-8080}"
JUDGE0_BASE_URL="${JUDGE0_BASE_URL:-http://10.0.1.2:${JUDGE0_LISTEN_PORT}}"

DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-gwx-cap-database-url}"
DB_USER="${DB_USER:-raghavs}"
DB_PASSWORD="${DB_PASSWORD:-}"
POSTGRES_HOST="${POSTGRES_HOST:-35.227.59.162}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-judge0}"

REDIS_HOST="${REDIS_HOST:-10.188.96.203}"
REDIS_PORT="${REDIS_PORT:-6379}"

JUDGE0_SECRET_KEY_BASE="${JUDGE0_SECRET_KEY_BASE:-cap-gcp-judge0-secret-change-me}"
BUILD_MODE="${BUILD_MODE:-docker}"
SKIP_JUDGE0_BUILD="${SKIP_JUDGE0_BUILD:-false}"
RESET_GCE_INSTANCE="${RESET_GCE_INSTANCE:-true}"

usage() {
  cat <<USAGE
Deploy the CAP Judge0 slim image to the internship GCE VM.

The VM exposes Judge0 on port ${JUDGE0_LISTEN_PORT} (mapped to container 2358).
Code execution should use JUDGE0_BASE_URL=${JUDGE0_BASE_URL}

Startup scripts run after stop/start, not after reboot/reset.
Requires compute.instances.setMetadata on the target VM.

Examples:
  scripts/deploy_gcp_judge0.sh
  SKIP_JUDGE0_BUILD=true scripts/deploy_gcp_judge0.sh
  RESET_GCE_INSTANCE=false scripts/deploy_gcp_judge0.sh
USAGE
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

secret_exists() {
  gcloud secrets describe "$1" \
    --project="$PROJECT_ID" \
    --format='value(name)' >/dev/null 2>&1
}

resolve_db_password() {
  if [[ -n "$DB_PASSWORD" ]]; then
    return
  fi

  if ! secret_exists "$DATABASE_URL_SECRET"; then
    die "Set DB_PASSWORD or ensure secret ${DATABASE_URL_SECRET} exists"
  fi

  local database_url
  database_url="$(gcloud secrets versions access latest \
    --secret="$DATABASE_URL_SECRET" \
    --project="$PROJECT_ID")"
  DB_PASSWORD="$(python3 - "$database_url" <<'PY'
import sys
import urllib.parse

raw = sys.argv[1]
normalized = raw.replace("postgresql+psycopg", "postgresql", 1)
parsed = urllib.parse.urlparse(normalized)
print(urllib.parse.unquote(parsed.password or ""))
PY
)"
  [[ -n "$DB_PASSWORD" ]] || die "Could not resolve DB password from ${DATABASE_URL_SECRET}"
}

judge0_image_uri() {
  printf '%s/%s/%s/%s:%s' \
    "$ARTIFACT_REGISTRY_HOST" \
    "$PROJECT_ID" \
    "$REPOSITORY" \
    "$JUDGE0_IMAGE_NAME" \
    "$IMAGE_TAG"
}

build_and_push() {
  local image
  image="$(judge0_image_uri)"

  if [[ "$SKIP_JUDGE0_BUILD" == "true" ]]; then
    log "Skipping Judge0 image build"
    return
  fi

  local repo_root
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  if [[ "$BUILD_MODE" == "cloudbuild" ]]; then
    log "Building and pushing Judge0 with Cloud Build"
    gcloud builds submit "$repo_root/docker/judge0" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --default-buckets-behavior=regional-user-owned-bucket \
      --tag="$image"
    return
  fi

  log "Building and pushing Judge0 for linux/amd64"
  docker buildx build \
    --platform=linux/amd64 \
    --provenance=false \
    --push \
    -t "$image" \
    "$repo_root/docker/judge0"
}

ensure_compute_artifact_access() {
  local compute_sa
  compute_sa="$(gcloud compute instances describe "$JUDGE0_GCE_INSTANCE" \
    --zone="$JUDGE0_GCE_ZONE" \
    --project="$PROJECT_ID" \
    --format='value(serviceAccounts[0].email)')"

  log "Ensuring ${compute_sa} can pull Artifact Registry images"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${compute_sa}" \
    --role="roles/artifactregistry.reader" \
    --condition=None >/dev/null 2>&1 || true
}

render_startup_script() {
  local image="$1"
  cat <<SCRIPT
#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends docker.io curl ca-certificates jq
systemctl enable --now docker

ACCESS_TOKEN="\$(curl -sf -H "Metadata-Flavor: Google" \\
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
  | jq -r .access_token)"
printf '%s' "\$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin \\
  "https://${ARTIFACT_REGISTRY_HOST}"

docker pull "${image}"

docker rm -f judge0-server judge0-worker >/dev/null 2>&1 || true

COMMON_ENV=(
  -e "POSTGRES_HOST=${POSTGRES_HOST}"
  -e "POSTGRES_PORT=${POSTGRES_PORT}"
  -e "POSTGRES_DB=${POSTGRES_DB}"
  -e "POSTGRES_USER=${DB_USER}"
  -e "POSTGRES_PASSWORD=${DB_PASSWORD}"
  -e "REDIS_HOST=${REDIS_HOST}"
  -e "REDIS_PORT=${REDIS_PORT}"
  -e "REDIS_PASSWORD="
  -e "SECRET_KEY_BASE=${JUDGE0_SECRET_KEY_BASE}"
  -e "RAILS_ENV=production"
  -e "RAILS_MAX_THREADS=2"
  -e "RAILS_SERVER_PROCESSES=1"
)

docker run -d --name judge0-server --restart unless-stopped --privileged \\
  -p 0.0.0.0:${JUDGE0_LISTEN_PORT}:2358 \\
  "\${COMMON_ENV[@]}" \\
  "${image}"

docker run -d --name judge0-worker --restart unless-stopped --privileged \\
  "\${COMMON_ENV[@]}" \\
  "${image}" ./scripts/workers

sleep 10
docker ps -a

for _ in \$(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${JUDGE0_LISTEN_PORT}/languages" >/dev/null; then
    exit 0
  fi
  sleep 5
done

echo "Judge0 failed to become ready on port ${JUDGE0_LISTEN_PORT}" >&2
docker logs judge0-server || true
docker logs judge0-worker || true
exit 1
SCRIPT
}

deploy_to_gce() {
  local image startup_script startup_path
  image="$(judge0_image_uri)"
  startup_script="$(render_startup_script "$image")"
  startup_path="$(mktemp "${TMPDIR:-/tmp}/cap-judge0-startup.XXXXXX.sh")"
  printf '%s\n' "$startup_script" >"$startup_path"

  log "Updating startup script on ${JUDGE0_GCE_INSTANCE}"
  gcloud compute instances add-metadata "$JUDGE0_GCE_INSTANCE" \
    --zone="$JUDGE0_GCE_ZONE" \
    --project="$PROJECT_ID" \
    --metadata-from-file="startup-script=${startup_path}"

  rm -f "$startup_path"

  if [[ "$RESET_GCE_INSTANCE" != "true" ]]; then
    log "Startup script updated. Stop and start the VM manually to apply it."
    return
  fi

  log "Stopping ${JUDGE0_GCE_INSTANCE} so the startup script can run on boot"
  gcloud compute instances stop "$JUDGE0_GCE_INSTANCE" \
    --zone="$JUDGE0_GCE_ZONE" \
    --project="$PROJECT_ID"

  log "Starting ${JUDGE0_GCE_INSTANCE}"
  gcloud compute instances start "$JUDGE0_GCE_INSTANCE" \
    --zone="$JUDGE0_GCE_ZONE" \
    --project="$PROJECT_ID"
}

wait_for_judge0() {
  log "Waiting for code execution health to report Judge0 as ready"
  local execution_url health attempt status
  execution_url="$(gcloud run services describe cap-code-execution-service \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || true)"

  if [[ -z "$execution_url" ]]; then
    log "Code execution service not found; skipping remote health wait"
    return
  fi

  for attempt in $(seq 1 36); do
    health="$(curl -sf "${execution_url}/api/v1/health" 2>/dev/null || true)"
    status="$(printf '%s' "$health" | python3 - <<'PY' || true
import json, sys
try:
    print(json.load(sys.stdin).get("status", ""))
except Exception:
    print("")
PY
)"
    if [[ "$status" == "ok" ]]; then
      log "Code execution health is ok"
      return
    fi
    sleep 10
  done

  die "Code execution is still degraded after Judge0 deploy"
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  command -v gcloud >/dev/null || die "Missing required command: gcloud"
  command -v python3 >/dev/null || die "Missing required command: python3"
  if [[ "$BUILD_MODE" == "docker" && "$SKIP_JUDGE0_BUILD" != "true" ]]; then
    command -v docker >/dev/null || die "Missing required command: docker"
    gcloud auth configure-docker "$ARTIFACT_REGISTRY_HOST" --quiet
  fi

  gcloud config set project "$PROJECT_ID" >/dev/null
  resolve_db_password
  build_and_push
  ensure_compute_artifact_access
  deploy_to_gce
  wait_for_judge0

  log "Judge0 deploy complete"
  printf 'JUDGE0_BASE_URL=%s\n' "$JUDGE0_BASE_URL"
}

main "$@"

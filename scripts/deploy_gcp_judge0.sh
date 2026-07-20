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
# The Judge0 server + worker + an actively-executing submission (up to
# MAX_MEMORY_LIMIT) do not fit in the 1 GB of an e2-micro: the first real
# submission drives the box into memory pressure and the API server wedges
# permanently (every endpoint, including /languages, times out). e2-medium
# (4 GB) runs the same workload comfortably. Enforce a minimum before deploy.
JUDGE0_GCE_MACHINE_TYPE="${JUDGE0_GCE_MACHINE_TYPE:-e2-medium}"

DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-gwx-cap-database-url}"
DB_USER="${DB_USER:-raghavs}"
DB_PASSWORD="${DB_PASSWORD:-}"
POSTGRES_HOST="${POSTGRES_HOST:-35.227.59.162}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-judge0}"

REDIS_HOST="${REDIS_HOST:-10.188.96.203}"
REDIS_PORT="${REDIS_PORT:-6379}"
# Leave empty when the Redis/Memorystore instance has AUTH disabled. An empty
# REDIS_PASSWORD must NOT be passed to Judge0: the Ruby redis client treats an
# empty-string password as truthy and still issues `AUTH ""`, which a no-auth
# Redis rejects, breaking every Resque-backed operation (submission enqueue,
# /workers) while DB-only endpoints (/languages) keep working.
REDIS_PASSWORD="${REDIS_PASSWORD:-}"

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
  # Only pass REDIS_PASSWORD when it is actually set. Passing an empty value
  # makes Judge0 send `AUTH ""` to a no-auth Redis and 500 on every submission.
  local redis_password_line=""
  if [[ -n "${REDIS_PASSWORD}" ]]; then
    redis_password_line="  -e \"REDIS_PASSWORD=${REDIS_PASSWORD}\""
  fi
  cat <<SCRIPT
#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive

# Judge0's isolate (v1) requires cgroup v1. Ubuntu 24.04 "Noble" defaults to
# the unified cgroup v2 hierarchy, under which even plain isolate box setup is
# unreliable. Force cgroup v1 via a GRUB drop-in. This only takes effect after
# the NEXT boot, so the first stop/start applies the flag and a subsequent
# stop/start actually runs the containers under cgroup v1. Idempotent.
mkdir -p /etc/default/grub.d
cat > /etc/default/grub.d/99-judge0-cgroupv1.cfg <<'GRUBCFG'
GRUB_CMDLINE_LINUX="\$GRUB_CMDLINE_LINUX systemd.unified_cgroup_hierarchy=0 systemd.legacy_systemd_cgroup_controller=1"
GRUBCFG
update-grub || true
if grep -q "systemd.unified_cgroup_hierarchy=0" /proc/cmdline; then
  echo "JUDGE0_CGROUP_V1_ACTIVE=yes"
else
  echo "JUDGE0_CGROUP_V1_ACTIVE=no (reboot again to apply)"
fi

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
${redis_password_line}
  -e "SECRET_KEY_BASE=${JUDGE0_SECRET_KEY_BASE}"
  -e "RAILS_ENV=production"
  -e "RAILS_MAX_THREADS=2"
  -e "RAILS_SERVER_PROCESSES=1"
  # Judge0 runs isolate with --cg whenever EITHER per-process/thread limit is
  # disabled (the default). isolate --cg needs the memory & cpuset cgroup v1
  # controllers, but Docker does not expose /sys/fs/cgroup/memory inside the
  # container, so `isolate --cg --init` fails, returns an empty box path, and
  # every submission dies with "No such file or directory - /box/script.py"
  # (status "Internal Error"). Enabling BOTH per-process limits makes Judge0
  # use plain `isolate --init`, which works. (Requires cgroup v1 on the host;
  # see the GRUB drop-in written by the startup script below.)
  -e "ENABLE_PER_PROCESS_AND_THREAD_TIME_LIMIT=true"
  -e "ENABLE_PER_PROCESS_AND_THREAD_MEMORY_LIMIT=true"
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
  # /languages only needs Postgres; /workers exercises the Redis/Resque path
  # that real submissions use. Gate on BOTH so a broken Redis connection does
  # not falsely report the deployment as ready.
  if curl -fsS "http://127.0.0.1:${JUDGE0_LISTEN_PORT}/languages" >/dev/null \\
    && curl -fsS "http://127.0.0.1:${JUDGE0_LISTEN_PORT}/workers" >/dev/null; then
    echo "JUDGE0_READY"
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

  # A running submission needs more RAM than an e2-micro provides; ensure the
  # VM is at least ${JUDGE0_GCE_MACHINE_TYPE} while it is stopped.
  local current_machine_type
  current_machine_type="$(gcloud compute instances describe "$JUDGE0_GCE_INSTANCE" \
    --zone="$JUDGE0_GCE_ZONE" \
    --project="$PROJECT_ID" \
    --format='value(machineType.basename())')"
  if [[ "$current_machine_type" != "$JUDGE0_GCE_MACHINE_TYPE" ]]; then
    log "Resizing ${JUDGE0_GCE_INSTANCE} from ${current_machine_type} to ${JUDGE0_GCE_MACHINE_TYPE}"
    gcloud compute instances set-machine-type "$JUDGE0_GCE_INSTANCE" \
      --zone="$JUDGE0_GCE_ZONE" \
      --project="$PROJECT_ID" \
      --machine-type="$JUDGE0_GCE_MACHINE_TYPE"
  fi

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

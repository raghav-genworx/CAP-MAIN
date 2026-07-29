#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
REGION="${REGION:-us-east1}"
ZONE="${ZONE:-us-east1-b}"
REPOSITORY="${REPOSITORY:-gwx-gar-intern-01}"
ARTIFACT_REGISTRY_HOST="${REGION}-docker.pkg.dev"
IMAGE_NAME="${IMAGE_NAME:-cap-judge0-js-node}"
IMAGE_TAG="${IMAGE_TAG:-node-22.17.1}"
BUILD_MODE="${BUILD_MODE:-gce-local}"

INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-judge0-js-01}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-medium}"
NETWORK="${NETWORK:-gwx-vpc-intern-01}"
SUBNET="${SUBNET:-gwx-sne-intern-01}"
FIREWALL_RULE="${FIREWALL_RULE:-gwx-allow-12359}"
NETWORK_TAG="${NETWORK_TAG:-gwx-allow-12359}"
LISTEN_PORT="${LISTEN_PORT:-12359}"

POSTGRES_DB="${POSTGRES_DB:-judge0_js}"
POSTGRES_USER="${POSTGRES_USER:-judge0_js}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-judge0-js-postgres-password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-judge0-js-redis-password}"
SECRET_KEY_BASE="${SECRET_KEY_BASE:-code-execution-service-gcp-isolated-judge0-js-secret}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

image_uri() {
  printf '%s/%s/%s/%s:%s' \
    "$ARTIFACT_REGISTRY_HOST" \
    "$PROJECT_ID" \
    "$REPOSITORY" \
    "$IMAGE_NAME" \
    "$IMAGE_TAG"
}

require_command() {
  command -v "$1" >/dev/null || die "Missing required command: $1"
}

ensure_firewall_rule() {
  if gcloud compute firewall-rules describe "$FIREWALL_RULE" \
    --project="$PROJECT_ID" >/dev/null 2>&1; then
    log "Firewall rule ${FIREWALL_RULE} already exists"
    return
  fi

  log "Creating firewall rule ${FIREWALL_RULE} for tcp:${LISTEN_PORT}"
  gcloud compute firewall-rules create "$FIREWALL_RULE" \
    --project="$PROJECT_ID" \
    --network="$NETWORK" \
    --direction=INGRESS \
    --action=ALLOW \
    --rules="tcp:${LISTEN_PORT}" \
    --source-ranges=0.0.0.0/0 \
    --target-tags="$NETWORK_TAG"
}

build_image() {
  local image
  image="$(image_uri)"

  if [[ "$BUILD_MODE" == "gce-local" ]]; then
    log "Skipping Cloud Build; ${INSTANCE_NAME} will build the image locally"
    return
  fi

  log "Building isolated Judge0 JS image with Cloud Build: ${image}"
  gcloud builds submit . \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --default-buckets-behavior=regional-user-owned-bucket \
    --tag="$image"
}

ensure_artifact_access() {
  if [[ "$BUILD_MODE" == "gce-local" ]]; then
    log "Skipping Artifact Registry IAM; local VM build does not pull a private image"
    return
  fi

  local project_number compute_sa
  project_number="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  compute_sa="${project_number}-compute@developer.gserviceaccount.com"

  log "Ensuring ${compute_sa} can pull Artifact Registry images"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${compute_sa}" \
    --role="roles/artifactregistry.reader" \
    --condition=None >/dev/null 2>&1 || true
}

render_startup_script() {
  local image="$1"
  local dockerfile active_languages archived_languages
  dockerfile="$(cat Dockerfile)"
  active_languages="$(cat languages/active.rb)"
  archived_languages="$(cat languages/archived.rb)"
  cat <<SCRIPT
#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive

mkdir -p /etc/default/grub.d
cat > /etc/default/grub.d/99-judge0-cgroupv1.cfg <<'GRUBCFG'
GRUB_CMDLINE_LINUX="\$GRUB_CMDLINE_LINUX systemd.unified_cgroup_hierarchy=0 systemd.legacy_systemd_cgroup_controller=1"
GRUBCFG

if ! grep -q "systemd.unified_cgroup_hierarchy=0" /proc/cmdline; then
  update-grub || true
  echo "JUDGE0_JS_REBOOTING_FOR_CGROUP_V1"
  shutdown -r now
  exit 0
fi

apt-get update
apt-get install -y --no-install-recommends docker.io curl ca-certificates jq
systemctl enable --now docker

mkdir -p /opt/judge0-js/languages
cat > /opt/judge0-js/Dockerfile <<'DOCKERFILE'
${dockerfile}
DOCKERFILE
cat > /opt/judge0-js/languages/active.rb <<'ACTIVE_RB'
${active_languages}
ACTIVE_RB
cat > /opt/judge0-js/languages/archived.rb <<'ARCHIVED_RB'
${archived_languages}
ARCHIVED_RB

if [[ "${BUILD_MODE}" == "gce-local" ]]; then
  docker build --no-cache -t judge0-js-node:gcp-local /opt/judge0-js
  JUDGE0_JS_IMAGE="judge0-js-node:gcp-local"
else
  ACCESS_TOKEN="\$(curl -sf -H "Metadata-Flavor: Google" \\
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
    | jq -r .access_token)"
  printf '%s' "\$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin \\
    "https://${ARTIFACT_REGISTRY_HOST}"
  docker pull "${image}"
  JUDGE0_JS_IMAGE="${image}"
fi

docker network create judge0-js-net >/dev/null 2>&1 || true
docker volume create judge0_js_gcp_postgres_data >/dev/null
docker volume create judge0_js_gcp_redis_data >/dev/null
docker volume create judge0_js_gcp_server_box >/dev/null
docker volume create judge0_js_gcp_worker_box >/dev/null

docker rm -f judge0-js-server judge0-js-worker judge0-js-db judge0-js-redis >/dev/null 2>&1 || true

docker run -d --name judge0-js-db --restart unless-stopped \\
  --network judge0-js-net \\
  -v judge0_js_gcp_postgres_data:/var/lib/postgresql/data \\
  -e "POSTGRES_DB=${POSTGRES_DB}" \\
  -e "POSTGRES_USER=${POSTGRES_USER}" \\
  -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \\
  postgres:13.16

docker run -d --name judge0-js-redis --restart unless-stopped \\
  --network judge0-js-net \\
  -v judge0_js_gcp_redis_data:/data \\
  redis:7.2.5 redis-server --appendonly yes --requirepass "${REDIS_PASSWORD}"

for _ in \$(seq 1 60); do
  if docker exec judge0-js-db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1 \\
    && docker exec judge0-js-redis redis-cli -a "${REDIS_PASSWORD}" ping >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

COMMON_ENV=(
  -e "JUDGE0_TELEMETRY_ENABLE=false"
  -e "ENABLE_WAIT_RESULT=true"
  -e "ENABLE_COMPILER_OPTIONS=true"
  -e "ENABLE_COMMAND_LINE_ARGUMENTS=true"
  -e "ENABLE_BATCHED_SUBMISSIONS=true"
  -e "ENABLE_CALLBACKS=false"
  -e "ENABLE_ADDITIONAL_FILES=false"
  -e "USE_DOCS_AS_HOMEPAGE=true"
  -e "POSTGRES_HOST=judge0-js-db"
  -e "POSTGRES_PORT=5432"
  -e "POSTGRES_DB=${POSTGRES_DB}"
  -e "POSTGRES_USER=${POSTGRES_USER}"
  -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
  -e "REDIS_HOST=judge0-js-redis"
  -e "REDIS_PORT=6379"
  -e "REDIS_PASSWORD=${REDIS_PASSWORD}"
  -e "CPU_TIME_LIMIT=2"
  -e "MAX_CPU_TIME_LIMIT=30"
  -e "CPU_EXTRA_TIME=1"
  -e "WALL_TIME_LIMIT=10"
  -e "MAX_WALL_TIME_LIMIT=45"
  -e "MEMORY_LIMIT=128000"
  -e "MAX_MEMORY_LIMIT=512000"
  -e "STACK_LIMIT=64000"
  -e "MAX_PROCESSES_AND_OR_THREADS=60"
  -e "MAX_FILE_SIZE=1024"
  -e "MAX_EXTRACT_SIZE=10240"
  -e "ENABLE_NETWORK=false"
  -e "ENABLE_PER_PROCESS_AND_THREAD_TIME_LIMIT=true"
  -e "ENABLE_PER_PROCESS_AND_THREAD_MEMORY_LIMIT=true"
  -e "RAILS_ENV=production"
  -e "RAILS_MAX_THREADS=2"
  -e "RAILS_SERVER_PROCESSES=1"
  -e "SECRET_KEY_BASE=${SECRET_KEY_BASE}"
)

docker run -d --name judge0-js-server --restart unless-stopped --privileged \\
  --network judge0-js-net \\
  -p "0.0.0.0:${LISTEN_PORT}:2358" \\
  -v judge0_js_gcp_server_box:/var/local/lib/isolate \\
  "\${COMMON_ENV[@]}" \\
  "\${JUDGE0_JS_IMAGE}"

docker run -d --name judge0-js-worker --restart unless-stopped --privileged \\
  --network judge0-js-net \\
  -v judge0_js_gcp_worker_box:/var/local/lib/isolate \\
  "\${COMMON_ENV[@]}" \\
  "\${JUDGE0_JS_IMAGE}" ./scripts/workers

for _ in \$(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${LISTEN_PORT}/languages" >/dev/null \\
    && curl -fsS "http://127.0.0.1:${LISTEN_PORT}/workers" >/dev/null; then
    echo "JUDGE0_JS_READY"
    docker ps -a
    exit 0
  fi
  sleep 5
done

echo "Judge0 JS failed to become ready on port ${LISTEN_PORT}" >&2
docker logs judge0-js-server || true
docker logs judge0-js-worker || true
exit 1
SCRIPT
}

create_or_update_instance() {
  local image startup_path
  image="$(image_uri)"
  startup_path="$(mktemp "${TMPDIR:-/tmp}/judge0-js-gcp-startup.XXXXXX.sh")"
  render_startup_script "$image" >"$startup_path"

  if gcloud compute instances describe "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" >/dev/null 2>&1; then
    log "Updating startup script on existing ${INSTANCE_NAME}"
    gcloud compute instances add-metadata "$INSTANCE_NAME" \
      --project="$PROJECT_ID" \
      --zone="$ZONE" \
      --metadata-from-file="startup-script=${startup_path}"

    log "Restarting ${INSTANCE_NAME}"
    gcloud compute instances reset "$INSTANCE_NAME" \
      --project="$PROJECT_ID" \
      --zone="$ZONE"
  else
    log "Creating isolated VM ${INSTANCE_NAME}"
    gcloud compute instances create "$INSTANCE_NAME" \
      --project="$PROJECT_ID" \
      --zone="$ZONE" \
      --machine-type="$MACHINE_TYPE" \
      --network-interface="network=${NETWORK},subnet=${SUBNET},stack-type=IPV4_ONLY" \
      --tags="$NETWORK_TAG,gwx-allow-ssh" \
      --image-family=ubuntu-2404-lts-amd64 \
      --image-project=ubuntu-os-cloud \
      --boot-disk-size=50GB \
      --boot-disk-type=pd-balanced \
      --metadata=enable-oslogin=TRUE \
      --metadata-from-file="startup-script=${startup_path}" \
      --scopes=https://www.googleapis.com/auth/cloud-platform
  fi

  rm -f "$startup_path"
}

main() {
  require_command gcloud

  gcloud config set project "$PROJECT_ID" >/dev/null
  build_image
  ensure_artifact_access
  ensure_firewall_rule
  create_or_update_instance

  log "Deployment requested. The VM may reboot once to enable cgroup v1 before starting Judge0."
  gcloud compute instances describe "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --format='value(networkInterfaces[0].accessConfigs[0].natIP)' \
    | awk -v port="$LISTEN_PORT" '{ print "JUDGE0_JS_URL=http://" $1 ":" port }'
}

main "$@"

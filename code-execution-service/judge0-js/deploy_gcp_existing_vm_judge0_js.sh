#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"
NETWORK_TAG="${NETWORK_TAG:-gwx-allow-12359}"
LISTEN_PORT="${LISTEN_PORT:-12359}"

POSTGRES_DB="${POSTGRES_DB:-judge0_js}"
POSTGRES_USER="${POSTGRES_USER:-judge0_js}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-judge0-js-postgres-password}"
REDIS_PASSWORD="${REDIS_PASSWORD:-judge0-js-redis-password}"
SECRET_KEY_BASE="${SECRET_KEY_BASE:-code-execution-service-gcp-existing-vm-judge0-js-secret}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null || die "Missing required command: $1"
}

render_startup_script() {
  local dockerfile active_languages archived_languages
  dockerfile="$(cat Dockerfile)"
  active_languages="$(cat languages/active.rb)"
  archived_languages="$(cat languages/archived.rb)"

  cat <<SCRIPT
#!/usr/bin/env bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive

# Preserve existing CAP Judge0 behavior first. The existing production
# containers keep their original names and are not removed or recreated here.
systemctl enable --now docker >/dev/null 2>&1 || true
docker start judge0-server judge0-worker >/dev/null 2>&1 || true

# Judge0 isolate works most reliably with cgroup v1. If this VM is not already
# booted with cgroup v1, apply the same GRUB setting used by the existing CAP
# deployment and reboot once before starting the isolated JS stack.
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

docker start judge0-server judge0-worker >/dev/null 2>&1 || true

# Preserve the existing Java hotfix startup behavior from this VM metadata.
(
  for _ in \$(seq 1 60); do
    if docker exec judge0-server bundle exec rails runner \\
      'Language.unscoped.find(62).update!(run_cmd: "/usr/bin/java -Xms16m -Xmx128m -XX:+UseSerialGC Main")'; then
      docker restart judge0-worker >/dev/null 2>&1 || true
      echo "JUDGE0_JAVA_HOTFIX_READY"
      exit 0
    fi
    sleep 5
  done
  echo "Judge0 Java hotfix failed" >&2
) &

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

docker build -t judge0-js-node:gcp-local /opt/judge0-js

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
  judge0-js-node:gcp-local

docker run -d --name judge0-js-worker --restart unless-stopped --privileged \\
  --network judge0-js-net \\
  -v judge0_js_gcp_worker_box:/var/local/lib/isolate \\
  "\${COMMON_ENV[@]}" \\
  judge0-js-node:gcp-local ./scripts/workers

for _ in \$(seq 1 120); do
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

main() {
  require_command gcloud

  local startup_path
  startup_path="$(mktemp "${TMPDIR:-/tmp}/judge0-js-existing-vm-startup.XXXXXX.sh")"
  render_startup_script >"$startup_path"

  gcloud config set project "$PROJECT_ID" >/dev/null

  log "Adding network tag ${NETWORK_TAG} to ${INSTANCE_NAME}"
  gcloud compute instances add-tags "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --tags="$NETWORK_TAG" >/dev/null

  log "Updating merged startup script on ${INSTANCE_NAME}"
  gcloud compute instances add-metadata "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --metadata-from-file="startup-script=${startup_path}"

  rm -f "$startup_path"

  log "Resetting ${INSTANCE_NAME} so the startup script runs"
  gcloud compute instances reset "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE"

  log "Startup script submitted. Judge0 JS will be available after build/startup completes."
  gcloud compute instances describe "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --format='value(networkInterfaces[0].accessConfigs[0].natIP)' \
    | awk -v port="$LISTEN_PORT" '{ print "JUDGE0_JS_URL=http://" $1 ":" port }'
}

main "$@"

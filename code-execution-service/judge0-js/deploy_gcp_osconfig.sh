#!/usr/bin/env bash
# Deploy the isolated judge0-js stack to the existing GCP VM WITHOUT rebooting it.
#
# Why OS Config instead of startup-script + reset:
#   * SSH on this VPC is IAP-only (gwx-allow-ssh-iap) and this principal lacks
#     iap.tunnelInstances.accessViaIAP, so there is no interactive shell.
#   * The VM's external IP is ephemeral, so stop/start would change it.
#   * `instances reset` is a hard power cycle.
#   An OS Policy Assignment `exec` resource runs an inline script on the running
#   VM with no reboot and no IP change.
#
# Safety: this only ever creates/removes containers, volumes and networks whose
# names are prefixed judge0-js / judge0_js. It never touches judge0-server,
# judge0-worker, or any other pre-existing container, image or volume.
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"
LISTEN_PORT="${LISTEN_PORT:-12359}"
ASSIGNMENT_ID="${ASSIGNMENT_ID:-judge0-js-deploy}"
NETWORK_TAG="${NETWORK_TAG:-gwx-allow-12359}"
REBUILD="${REBUILD:-always}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not found"

for f in Dockerfile docker-compose.yml judge0.conf languages/active.rb languages/archived.rb; do
  [ -f "$f" ] || die "missing required file: $f"
done

# ---------------------------------------------------------------------------
# Pack the isolated stack definition. Embedding a base64 tarball avoids any
# heredoc/quoting interaction between this script, YAML and the remote shell.
# ---------------------------------------------------------------------------
log "Packing judge0-js stack definition"
PAYLOAD="$(tar czf - Dockerfile docker-compose.yml judge0.conf languages | base64 | tr -d '\n')"
printf 'payload bytes: %s\n' "${#PAYLOAD}"

# Content revision of the stack definition. `validate` looks for a marker named
# after it, so enforce runs exactly once per revision: no re-enforce loop while
# healthy, but an automatic re-run whenever any of these files change. Checking
# only "is language 63 listed" is not enough -- that stayed true while every
# submission failed with an Internal Error.
REV="$(cat Dockerfile docker-compose.yml judge0.conf languages/active.rb languages/archived.rb \
  | shasum -a 256 | cut -c1-12)"
log "Stack revision: ${REV}"

# ---------------------------------------------------------------------------
# The long-running deploy body. Written to /opt/judge0-js/deploy.sh on the VM
# and launched detached via systemd-run so the ~20 min image build cannot be
# killed by any OS Config agent step timeout.
# ---------------------------------------------------------------------------
read -r -d '' DEPLOY_BODY <<'DEPLOY_EOF' || true
#!/bin/bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive

PORT="__LISTEN_PORT__"
DIR=/opt/judge0-js
GA="http://metadata.google.internal/computeMetadata/v1/instance/guest-attributes/judge0-js"

put() {
  curl -fsS -X PUT -H "Metadata-Flavor: Google" --data "$2" "${GA}/$1" >/dev/null 2>&1 || true
}
st() { echo "JUDGE0_JS_STATUS=$1"; put status "$1"; }
# There is no SSH to this VM, so a failure must carry its own evidence out
# through guest attributes -- otherwise the reason is stranded in deploy.log.
fail() {
  st "failed_line_$1"
  put logtail "$(tail -c 900 "$DIR/deploy.log" 2>/dev/null | tr -cd '\11\12\15\40-\176')"
}
trap 'fail ${LINENO}' ERR

mkdir -p "$DIR"
exec >>"$DIR/deploy.log" 2>&1
echo "=== deploy start $(date -Is) ==="

st installing_prereqs
# Deliberately do NOT `apt-get install docker.io` unconditionally: if this VM's
# engine came from Docker's own repo (docker-ce), pulling in Ubuntu's docker.io
# makes apt remove docker-ce, which would tear down every running container --
# including the pre-existing Judge0 we must preserve. Only install if absent.
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -o Acquire::Retries=3
  apt-get install -y --no-install-recommends docker.io
fi
MISSING=""
for p in curl jq; do command -v "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"; done
if [ -n "$MISSING" ]; then
  apt-get update -o Acquire::Retries=3
  apt-get install -y --no-install-recommends ca-certificates $MISSING
fi
systemctl enable --now docker

# Compose v2 as a standalone CLI plugin binary -- no apt dependency resolution,
# so the running engine and its containers are never at risk.
if ! docker compose version >/dev/null 2>&1; then
  st installing_compose_plugin
  mkdir -p /usr/local/lib/docker/cli-plugins
  curl -fSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m)" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose
  docker compose version
fi

# -------------------------------------------------------------------------
# 1. Record rollback state BEFORE changing anything. Never mutates anything.
# -------------------------------------------------------------------------
st recording_rollback_state
mkdir -p "$DIR/rollback"
# Recording diagnostics must never abort the deploy, so this whole section runs
# with errexit and the ERR trap suspended.
set +e
trap - ERR
{
  echo "### captured $(date -Is)"
  echo "### uname"; uname -a
  echo "### cgroup fs"; stat -fc %T /sys/fs/cgroup
  echo "### /proc/cmdline"; cat /proc/cmdline
  echo "### df -h /"; df -h /
  echo "### free -h"; free -h
  echo "### docker version"; docker version
  echo "### docker ps -a"; docker ps -a
  echo "### docker images"; docker images
  echo "### docker volume ls"; docker volume ls
  echo "### docker network ls"; docker network ls
  echo "### compose-managed containers"
  # NOTE: in `docker ps --format`, .Labels is a comma-joined STRING, not a map,
  # so `index .Labels "k"` is a template error and makes docker exit non-zero.
  # The per-label accessor is the `.Label` method.
  docker ps -a --filter label=com.docker.compose.project \
    --format '{{.Names}}|proj={{.Label "com.docker.compose.project"}}|dir={{.Label "com.docker.compose.project.working_dir"}}|files={{.Label "com.docker.compose.project.config_files"}}'
  for c in judge0-server judge0-worker; do
    echo "### docker inspect ${c}"
    docker inspect "$c" 2>&1 || echo "(absent)"
  done
  echo "### compose files on disk"
  find /opt /srv /root /home /etc -maxdepth 5 -name 'docker-compose*.y*ml' 2>/dev/null
} >"$DIR/rollback/state.txt" 2>&1

# Publish a compact, guest-attribute-sized summary of the pre-existing stack.
PROD_PS="$(docker ps -a --format '{{.Names}}:{{.Image}}:{{.State}}' 2>/dev/null | head -c 900)"
put rollback_ps "${PROD_PS:-none}"
PROD_PROJ="$(docker ps -a --filter label=com.docker.compose.project \
  --format '{{.Label "com.docker.compose.project"}}@{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null \
  | sort -u | head -c 600)"
put rollback_compose "${PROD_PROJ:-none}"
put cgroup_fs "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)"
put disk_free "$(df -h / | awk 'NR==2{print $4" free of "$2}')"
put docker_version "$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
set -e
trap 'fail ${LINENO}' ERR

# -------------------------------------------------------------------------
# 2. Reclaim space from the previous failed build. Only build cache and
#    dangling layers -- never `image prune -a`, which would delete the
#    pre-existing Judge0 images that are needed for rollback.
# -------------------------------------------------------------------------
st reclaiming_disk
docker builder prune -af || true
docker image prune -f || true
apt-get clean || true

# -------------------------------------------------------------------------
# 3. Materialise the isolated stack definition.
# -------------------------------------------------------------------------
st writing_stack_files
rm -rf "$DIR/Dockerfile" "$DIR/docker-compose.yml" "$DIR/judge0.conf" "$DIR/languages"
base64 -d "$DIR/payload.b64" | tar xzf - -C "$DIR"
test -x /bin/true
grep -q 'id: 63' "$DIR/languages/active.rb" || { st missing_language_63; exit 1; }

# -------------------------------------------------------------------------
# 4. Clear only leftovers from earlier judge0-js attempts (never production).
# -------------------------------------------------------------------------
st clearing_previous_js_attempt
docker rm -f judge0-js-server judge0-js-worker judge0-js-db judge0-js-redis >/dev/null 2>&1 || true
docker network rm judge0-js-net >/dev/null 2>&1 || true
for v in judge0_js_gcp_postgres_data judge0_js_gcp_redis_data judge0_js_gcp_server_box judge0_js_gcp_worker_box; do
  docker volume rm -f "$v" >/dev/null 2>&1 || true
done

cd "$DIR"

st compose_down
docker compose down -v || true

# REBUILD=always  -> always `build --no-cache` (the documented flow)
# REBUILD=missing -> reuse an existing judge0-js-node:local (config-only changes
#                   need no rebuild, since judge0.conf is bind-mounted)
if [ "__REBUILD__" = "always" ] || ! docker image inspect judge0-js-node:local >/dev/null 2>&1; then
  st building_image
  docker compose build --no-cache
else
  st reusing_existing_image
  echo "reusing judge0-js-node:local (REBUILD=__REBUILD__)"
fi

st verifying_node_in_image
NODE_V="$(docker compose run --rm --no-deps --entrypoint /bin/sh judge0-server -lc 'test -x /usr/bin/node && /usr/bin/node --version')"
put node_version "$NODE_V"
echo "node in image: $NODE_V"

st compose_up
docker compose up -d

# -------------------------------------------------------------------------
# 5. Verify.
# -------------------------------------------------------------------------
st waiting_for_languages
LANGS=""
for _ in $(seq 1 120); do
  if LANGS="$(curl -fsS "http://127.0.0.1:${PORT}/languages" 2>/dev/null)"; then
    if printf '%s' "$LANGS" | jq -e '.[] | select(.id == 63 and .name == "JavaScript (Node.js)")' >/dev/null 2>&1; then
      break
    fi
  fi
  sleep 5
done

if ! printf '%s' "$LANGS" | jq -e '.[] | select(.id == 63)' >/dev/null 2>&1; then
  st language_63_missing
  put languages "$(printf '%s' "$LANGS" | head -c 800)"
  docker compose ps
  docker compose logs --tail=120 judge0-server
  exit 1
fi

put languages "$(printf '%s' "$LANGS" | jq -c '[.[]|{id,name}]' | head -c 900)"
put lang63 "present"

st waiting_for_worker
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${PORT}/workers" >/dev/null 2>&1 && break
  sleep 5
done

st testing_javascript
JS_RESP="$(curl -fsS -X POST "http://127.0.0.1:${PORT}/submissions?wait=true" \
  -H "Content-Type: application/json" \
  -d '{"language_id":63,"source_code":"const fs = require(\"fs\"); console.log(fs.readFileSync(0, \"utf8\").trim());","stdin":"hello javascript"}' 2>&1 || true)"
echo "js response: $JS_RESP"
put js_raw "$(printf '%s' "$JS_RESP" | head -c 900)"
JS_OUT="$(printf '%s' "$JS_RESP" | jq -r '.stdout // ""' 2>/dev/null | tr -d '\n')"
JS_DESC="$(printf '%s' "$JS_RESP" | jq -r '.status.description // "unknown"' 2>/dev/null)"
put js_stdout "${JS_OUT:-empty}"
put js_status "${JS_DESC:-unknown}"

# Regression-check the four pre-existing languages still run in this image.
st testing_other_languages
probe() { # id, source, expected -> prints detail line, then "ok"/"MISMATCH"
  local id="$1" src="$2" want="$3" body resp out desc
  body="$(jq -nc --arg s "$src" --argjson i "$id" '{language_id:$i, source_code:$s}')"
  # A failed curl/jq must not trip errexit and abort the whole deploy.
  resp="$(curl -fsS -X POST "http://127.0.0.1:${PORT}/submissions?wait=true" \
    -H "Content-Type: application/json" -d "$body" 2>/dev/null || true)"
  out="$(printf '%s' "$resp" | jq -r '.stdout // ""' 2>/dev/null | tr -d '\n\r' || true)"
  desc="$(printf '%s' "$resp" | jq -r '.status.description // "no-response"' 2>/dev/null || true)"
  echo "lang ${id} -> '${out}' status='${desc}' (want '${want}')"
  # Record the failure detail so a mismatch is diagnosable without SSH.
  [ "$out" = "$want" ] || put "lang${id}_fail" "$(printf '%s' "$resp" | head -c 700)"
  if [ "$out" = "$want" ]; then echo "ok"; else echo "MISMATCH"; fi
}
C_OK="$(probe 50 '#include <stdio.h>
int main(void){printf("c-ok\n");return 0;}' 'c-ok' | tail -1)"
CPP_OK="$(probe 54 '#include <iostream>
int main(){std::cout<<"cpp-ok"<<std::endl;return 0;}' 'cpp-ok' | tail -1)"
JAVA_OK="$(probe 62 'public class Main{public static void main(String[] a){System.out.println("java-ok");}}' 'java-ok' | tail -1)"
PY_OK="$(probe 71 'print("py-ok")' 'py-ok' | tail -1)"
put lang_matrix "c=${C_OK} cpp=${CPP_OK} java=${JAVA_OK} py=${PY_OK}"

put compose_ps "$(docker compose ps --format '{{.Name}}:{{.State}}' 2>/dev/null | tr '\n' ' ' | head -c 600)"
put cgroups_mode "$(printf '%s' "$JS_RESP" | jq -r 'if .memory then "per-process (max-rss)" else "unknown" end' 2>/dev/null)"

if [ "$JS_OUT" = "hello javascript" ] \
   && [ "${C_OK}" = "ok" ] && [ "${CPP_OK}" = "ok" ] \
   && [ "${JAVA_OK}" = "ok" ] && [ "${PY_OK}" = "ok" ]; then
  # Marker makes the policy's validate step compliant, so enforce will not
  # re-run for this revision.
  touch "$DIR/.ready-__REV__"
  st ready
else
  [ "$JS_OUT" = "hello javascript" ] || st js_output_mismatch
  [ "$JS_OUT" = "hello javascript" ] && st other_language_mismatch
  exit 1
fi
echo "=== deploy end $(date -Is) ==="
DEPLOY_EOF

DEPLOY_BODY="${DEPLOY_BODY//__LISTEN_PORT__/$LISTEN_PORT}"
DEPLOY_BODY="${DEPLOY_BODY//__REBUILD__/$REBUILD}"
DEPLOY_BODY="${DEPLOY_BODY//__REV__/$REV}"
DEPLOY_B64="$(printf '%s' "$DEPLOY_BODY" | base64 | tr -d '\n')"

# ---------------------------------------------------------------------------
# The OS Config exec resource. `enforce` only stages files and launches the
# detached unit, so it returns in seconds. `validate` reports compliance so a
# healthy VM is not redeployed on every agent poll.
# ---------------------------------------------------------------------------
# Trailing X's only -- BSD/macOS mktemp does not substitute a mid-name XXXXXX.
POLICY_FILE="$(mktemp "${TMPDIR:-/tmp}/judge0-js-ospolicy-XXXXXX")"
cat >"$POLICY_FILE" <<YAML
osPolicies:
  - id: judge0-js
    mode: ENFORCEMENT
    resourceGroups:
      - resources:
          - id: deploy-judge0-js
            exec:
              validate:
                interpreter: SHELL
                script: |
                  if [ -f /opt/judge0-js/.ready-${REV} ] && \
                     curl -fsS --max-time 5 http://127.0.0.1:${LISTEN_PORT}/languages 2>/dev/null | grep -q '"id":63'; then
                    exit 100
                  fi
                  exit 101
              enforce:
                interpreter: SHELL
                script: |
                  set -e
                  mkdir -p /opt/judge0-js
                  cat >/opt/judge0-js/payload.b64 <<'PAYLOAD_EOF'
                  ${PAYLOAD}
                  PAYLOAD_EOF
                  sed -i 's/^[[:space:]]*//' /opt/judge0-js/payload.b64
                  cat >/opt/judge0-js/deploy.b64 <<'DEPLOYB64_EOF'
                  ${DEPLOY_B64}
                  DEPLOYB64_EOF
                  sed -i 's/^[[:space:]]*//' /opt/judge0-js/deploy.b64
                  base64 -d /opt/judge0-js/deploy.b64 >/opt/judge0-js/deploy.sh
                  chmod +x /opt/judge0-js/deploy.sh
                  systemctl reset-failed judge0-js-deploy.service 2>/dev/null || true
                  systemd-run --unit=judge0-js-deploy --collect --service-type=oneshot \
                    /bin/bash /opt/judge0-js/deploy.sh
                  exit 100
instanceFilter:
  inclusionLabels:
    - labels:
        judge0-js-deploy: "true"
rollout:
  disruptionBudget:
    fixed: 1
  minWaitDuration: 60s
YAML

log "Rendered OS policy: $POLICY_FILE ($(wc -c <"$POLICY_FILE") bytes)"

gcloud config set project "$PROJECT_ID" >/dev/null

log "Ensuring network tag ${NETWORK_TAG} on ${INSTANCE_NAME}"
gcloud compute instances add-tags "$INSTANCE_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" --tags="$NETWORK_TAG" >/dev/null 2>&1 || true

log "Labelling ${INSTANCE_NAME} so the assignment targets only this VM"
gcloud compute instances add-labels "$INSTANCE_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" --labels=judge0-js-deploy=true >/dev/null

# --async throughout: the long-running operation can take ~30 min to be reported
# as finished even though the agent begins enforcing within a couple of minutes,
# so blocking on it just hides progress. Track real progress via guest
# attributes (./watch_gcp_judge0_js.sh).
if gcloud compute os-config os-policy-assignments describe "$ASSIGNMENT_ID" \
     --project="$PROJECT_ID" --location="$ZONE" >/dev/null 2>&1; then
  log "Updating existing OS policy assignment ${ASSIGNMENT_ID}"
  gcloud compute os-config os-policy-assignments update "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
else
  log "Creating OS policy assignment ${ASSIGNMENT_ID}"
  gcloud compute os-config os-policy-assignments create "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
fi

rm -f "$POLICY_FILE"

log "Assignment applied. The VM was NOT rebooted and its IP is unchanged."
cat <<NEXT

Watch progress (guest attributes are the status channel):

  gcloud compute instances get-guest-attributes ${INSTANCE_NAME} \\
    --project=${PROJECT_ID} --zone=${ZONE} --query-path=judge0-js/status

  ./watch_gcp_judge0_js.sh

Once status reads "ready":

  curl http://\$(gcloud compute instances describe ${INSTANCE_NAME} \\
    --project=${PROJECT_ID} --zone=${ZONE} \\
    --format='value(networkInterfaces[0].accessConfigs[0].natIP)'):${LISTEN_PORT}/languages
NEXT

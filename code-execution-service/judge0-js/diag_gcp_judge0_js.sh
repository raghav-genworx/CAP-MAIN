#!/usr/bin/env bash
# Gather judge0-js diagnostics from the existing GCP VM and publish them through
# guest attributes (the only readable channel without SSH).
#
# Read-only: inspects containers and logs, reuses the already-built image, and
# never rebuilds. Nothing outside the judge0-js stack is touched.
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"
ASSIGNMENT_ID="${ASSIGNMENT_ID:-judge0-js-diag}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

read -r -d '' DIAG_BODY <<'DIAG_EOF' || true
#!/bin/bash
set -uo pipefail
DIR=/opt/judge0-js
GA="http://metadata.google.internal/computeMetadata/v1/instance/guest-attributes/judge0-diag"

put() {
  curl -fsS -X PUT -H "Metadata-Flavor: Google" \
    --data "$(printf '%s' "$2" | tr -cd '\11\12\15\40-\176' | head -c 900)" \
    "${GA}/$1" >/dev/null 2>&1 || true
}

cd "$DIR" 2>/dev/null || exit 0

put ps_all      "$(docker compose ps -a --format '{{.Name}}:{{.State}}:{{.ExitCode}}' 2>&1)"
put mem         "$(free -m | tr -s ' ' 2>&1)"
put oom         "$(dmesg 2>/dev/null | grep -ciE 'oom|killed process') killed=$(dmesg 2>/dev/null | grep -oiE 'Killed process [0-9]+ \([^)]*\)' | tail -3 | tr '\n' ';')"
put cgroup_ls   "$(ls /sys/fs/cgroup 2>&1 | tr '\n' ' ')"
put boxroot     "$(ls -ld /var/local/lib/isolate 2>&1; docker compose exec -T judge0-worker ls -ld /var/local/lib/isolate 2>&1)"

# Worker log is where the isolate failure is explained.
W="$(docker compose logs --tail=120 judge0-worker 2>&1)"
put worker_1 "$(printf '%s' "$W" | tail -40 | head -14)"
put worker_2 "$(printf '%s' "$W" | tail -26 | head -13)"
put worker_3 "$(printf '%s' "$W" | tail -13)"

S="$(docker compose logs --tail=60 judge0-server 2>&1)"
put server_1 "$(printf '%s' "$S" | tail -24 | head -12)"
put server_2 "$(printf '%s' "$S" | tail -12)"

put redis_log "$(docker compose logs --tail=12 judge0-redis 2>&1 | tail -6)"

# Ask isolate directly why --init fails. This is the crux of the /box/script.js
# error: judge0 shells out to `isolate --init` and uses its stdout as the work
# directory, so an empty/failed result yields the path "/box/script.js".
put isolate_bin  "$(docker compose exec -T judge0-worker sh -lc 'command -v isolate; ls -l $(command -v isolate); ls -l /usr/local/etc/isolate 2>&1 | head -3' 2>&1)"
put isolate_ver  "$(docker compose exec -T judge0-worker sh -lc 'isolate --version 2>&1 | head -3' 2>&1)"
# As the judge0 user -- exactly how the real job invokes it (no sudo).
put isolate_user "$(docker compose exec -T judge0-worker sh -lc 'isolate --cg -b 0 --init 2>&1; echo "rc=$?"' 2>&1)"
put isolate_sudo "$(docker compose exec -T judge0-worker sh -lc 'sudo isolate --cg -b 1 --init 2>&1; echo "rc=$?"' 2>&1)"
put isolate_nocg "$(docker compose exec -T judge0-worker sh -lc 'isolate -b 2 --init 2>&1; echo "rc=$?"' 2>&1)"
put worker_env   "$(docker compose exec -T judge0-worker sh -lc 'echo COUNT=$COUNT BOX_ROOT=$BOX_ROOT nproc=$(nproc) whoami=$(whoami)' 2>&1)"
put cg_inside    "$(docker compose exec -T judge0-worker sh -lc 'stat -fc %T /sys/fs/cgroup; ls /sys/fs/cgroup | tr "\n" " "' 2>&1)"

put done "yes"
DIAG_EOF

DIAG_B64="$(printf '%s' "$DIAG_BODY" | base64 | tr -d '\n')"

POLICY_FILE="$(mktemp "${TMPDIR:-/tmp}/judge0-js-diag-XXXXXX")"
cat >"$POLICY_FILE" <<YAML
osPolicies:
  - id: judge0-js-diag
    mode: ENFORCEMENT
    resourceGroups:
      - resources:
          - id: diag
            exec:
              validate:
                interpreter: SHELL
                script: |
                  exit 101
              enforce:
                interpreter: SHELL
                script: |
                  set -e
                  mkdir -p /opt/judge0-js
                  cat >/opt/judge0-js/diag.b64 <<'DIAGB64_EOF'
                  ${DIAG_B64}
                  DIAGB64_EOF
                  sed -i 's/^[[:space:]]*//' /opt/judge0-js/diag.b64
                  base64 -d /opt/judge0-js/diag.b64 >/opt/judge0-js/diag.sh
                  chmod +x /opt/judge0-js/diag.sh
                  systemctl reset-failed judge0-js-diag.service 2>/dev/null || true
                  systemd-run --unit=judge0-js-diag --collect --service-type=oneshot \
                    /bin/bash /opt/judge0-js/diag.sh
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

gcloud config set project "$PROJECT_ID" >/dev/null

if gcloud compute os-config os-policy-assignments describe "$ASSIGNMENT_ID" \
     --project="$PROJECT_ID" --location="$ZONE" >/dev/null 2>&1; then
  log "Updating diagnostic assignment"
  gcloud compute os-config os-policy-assignments update "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
else
  log "Creating diagnostic assignment"
  gcloud compute os-config os-policy-assignments create "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
fi

rm -f "$POLICY_FILE"
log "Submitted (async). Read results with:"
cat <<'NEXT'
  gcloud compute instances get-guest-attributes gwx-gce-intern-01 \
    --project=gwx-internship-2026-01 --zone=us-east1-b | grep judge0-diag
NEXT

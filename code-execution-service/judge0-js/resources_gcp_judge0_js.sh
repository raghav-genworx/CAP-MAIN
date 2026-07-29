#!/usr/bin/env bash
# Measure judge0-js resource usage (disk, RAM, image and volume sizes) on the
# existing GCP VM and publish the numbers through guest attributes.
#
# Read-only: it inspects only. No container, image, volume or config is changed.
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"
ASSIGNMENT_ID="${ASSIGNMENT_ID:-judge0-js-resources}"

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

read -r -d '' BODY <<'BODY_EOF' || true
#!/bin/bash
set -uo pipefail
GA="http://metadata.google.internal/computeMetadata/v1/instance/guest-attributes/judge0-res"
put() {
  curl -fsS -X PUT -H "Metadata-Flavor: Google" \
    --data "$(printf '%s' "$2" | tr -cd '\11\12\15\40-\176' | head -c 900)" \
    "${GA}/$1" >/dev/null 2>&1 || true
}
cd /opt/judge0-js 2>/dev/null || exit 0

# ---- host ----------------------------------------------------------------
put host "$(uname -srm); cpus=$(nproc); model=$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo | sed 's/^ *//'); uptime=$(uptime -p 2>/dev/null); load=$(cut -d' ' -f1-3 /proc/loadavg)"
put os   "$(. /etc/os-release; echo "$PRETTY_NAME"); kernel=$(uname -r); cgroup=$(stat -fc %T /sys/fs/cgroup)"

# ---- RAM -----------------------------------------------------------------
put mem_h  "$(free -h | sed 's/  */ /g')"
put mem_m  "$(free -m | awk 'NR==1{next} {print $1" total="$2"M used="$3"M free="$4"M avail="$7"M"}' | tr '\n' ' | ')"

# ---- disk ----------------------------------------------------------------
put disk_fs   "$(df -h / /mnt/* 2>/dev/null | sed 's/  */ /g' | tr '\n' ' | ')"
put disk_block "$(lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT 2>/dev/null | sed 's/  */ /g' | tr '\n' ' | ')"
put disk_docker "/var/lib/docker total: $(du -sh /var/lib/docker 2>/dev/null | cut -f1)"

# ---- docker overall ------------------------------------------------------
put docker_df "$(docker system df 2>/dev/null | sed 's/  */ /g' | tr '\n' ' | ')"

# ---- image sizes ---------------------------------------------------------
put img_judge0js "$(docker image inspect judge0-js-node:local --format '{{.RepoTags}} size={{.Size}}B virtual' 2>/dev/null); human=$(docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' 2>/dev/null | grep judge0-js-node | head -1)"
put img_all "$(docker images --format '{{.Repository}}:{{.Tag}}={{.Size}}' 2>/dev/null | sort | tr '\n' ' ')"

# Layer contribution of the judge0-js image (what Node/JDK/bundle each cost).
put img_layers "$(docker history judge0-js-node:local --human --format '{{.Size}} {{.CreatedBy}}' 2>/dev/null | grep -vE '^0B' | head -12 | cut -c1-70 | tr '\n' ' | ')"

# ---- per-container RAM / CPU --------------------------------------------
# NOTE: `docker stats` reports mem=0B on this host because there is no cgroup v1
# `memory` controller (same kernel limitation that forced --cg off). Sum process
# RSS inside each container instead, which does not depend on memcg.
put stats "$(docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' judge0-js-server judge0-js-worker judge0-js-db judge0-js-redis 2>/dev/null | tr '\n' ' | ')"
# `docker top` runs ps on the HOST, so it works for postgres/redis too -- those
# images have no procps, which is why an in-container `ps` reported 0.
put rss "$(for c in judge0-js-server judge0-js-worker judge0-js-db judge0-js-redis judge0-server judge0-worker; do
  v=$(docker top "$c" -o rss 2>/dev/null | awk 'NR>1{s+=$1} END{printf "%d", s/1024}')
  n=$(docker top "$c" -o rss 2>/dev/null | awk 'NR>1{c++} END{print c+0}')
  echo -n "$c=${v:-na}MiB(${n:-0}p) "
done)"
# Deduplicated per-image disk usage (shared layers counted once).
put df_images "$(docker system df -v 2>/dev/null | awk '/^REPOSITORY/{f=1;next} /^CONTAINER ID/{f=0} f && NF>4{print $1":"$2"="$(NF-2)}' | tr '\n' ' ' | head -c 880)"
# Load average is high; identify what is actually burning CPU.
put top_cpu "$(ps -eo pcpu,rss,comm --sort=-pcpu --no-headers 2>/dev/null | head -8 | awk '{printf "%s%%cpu %.0fMiB %s | ", $1, $2/1024, $3}')"
put restarts "$(for c in judge0-server judge0-worker judge0-js-server judge0-js-worker; do
  echo -n "$c=$(docker inspect -f '{{.RestartCount}}/{{.State.Status}}' "$c" 2>/dev/null || echo n/a) "; done)"

# ---- container writable layers ------------------------------------------
put csize "$(docker ps -a --size --format '{{.Names}}={{.Size}}' 2>/dev/null | grep judge0-js | tr '\n' ' ')"

# ---- volumes -------------------------------------------------------------
put vols "$(for v in judge0_js_postgres_data judge0_js_redis_data judge0_js_server_box judge0_js_worker_box; do p=/var/lib/docker/volumes/$v/_data; [ -d "$p" ] && echo -n "$v=$(du -sh $p 2>/dev/null | cut -f1) "; done)"

# ---- judge0-js total footprint ------------------------------------------
# Use the UNPACKED sizes reported by `docker images`. `docker image inspect
# .Size` under the containerd image store reports compressed content size and is
# ~4x smaller, which badly understates real disk usage.
put footprint "$(docker images --format '{{.Repository}}:{{.Tag}}={{.Size}}' 2>/dev/null \
  | grep -E 'judge0-js-node|postgres:13.16|redis:7.2.5' | tr '\n' ' ') \
volumes=$(du -sh -c /var/lib/docker/volumes/judge0_js_* 2>/dev/null | tail -1 | cut -f1) \
opt_dir=$(du -sh /opt/judge0-js 2>/dev/null | cut -f1)"
put docker_root "$(docker info --format '{{.DockerRootDir}} driver={{.Driver}}' 2>/dev/null); du=$(du -sh "$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)" 2>/dev/null | cut -f1)"

# ---- what the pre-existing CAP judge0 still occupies ---------------------
put cap_imgs "$(docker images --format '{{.Repository}}:{{.Tag}}={{.Size}}' 2>/dev/null | grep -iE 'cap-judge0|judge0-slim|cap' | tr '\n' ' ')"
put cap_stats "$(docker stats --no-stream --format '{{.Name}} mem={{.MemUsage}}' judge0-server judge0-worker 2>/dev/null | tr '\n' ' | ')"

put done yes
BODY_EOF

B64="$(printf '%s' "$BODY" | base64 | tr -d '\n')"
POLICY_FILE="$(mktemp "${TMPDIR:-/tmp}/judge0-res-XXXXXX")"
cat >"$POLICY_FILE" <<YAML
osPolicies:
  - id: judge0-js-resources
    mode: ENFORCEMENT
    resourceGroups:
      - resources:
          - id: measure
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
                  cat >/opt/judge0-js/res.b64 <<'RESB64_EOF'
                  ${B64}
                  RESB64_EOF
                  sed -i 's/^[[:space:]]*//' /opt/judge0-js/res.b64
                  base64 -d /opt/judge0-js/res.b64 >/opt/judge0-js/res.sh
                  chmod +x /opt/judge0-js/res.sh
                  systemctl reset-failed judge0-js-res.service 2>/dev/null || true
                  systemd-run --unit=judge0-js-res --collect --service-type=oneshot \
                    /bin/bash /opt/judge0-js/res.sh
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
  log "Updating resource-measurement assignment"
  gcloud compute os-config os-policy-assignments update "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
else
  log "Creating resource-measurement assignment"
  gcloud compute os-config os-policy-assignments create "$ASSIGNMENT_ID" \
    --project="$PROJECT_ID" --location="$ZONE" --file="$POLICY_FILE" --async
fi
rm -f "$POLICY_FILE"

log "Submitted. Results appear under guest-attribute namespace judge0-res."
cat <<'NEXT'
  gcloud compute instances get-guest-attributes gwx-gce-intern-01 \
    --project=gwx-internship-2026-01 --zone=us-east1-b | grep judge0-res

  Remember to delete this assignment afterwards (its validate always reports
  non-compliant, so it re-measures on every agent poll):
  gcloud compute os-config os-policy-assignments delete judge0-js-resources \
    --project=gwx-internship-2026-01 --location=us-east1-b --quiet
NEXT

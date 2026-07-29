#!/usr/bin/env bash
# Poll the judge0-js deployment status on the existing GCP VM.
#
# The VM is not SSH-reachable from here (IAP-only VPC, and this principal lacks
# iap.tunnelInstances.accessViaIAP), so the deploy script reports progress
# through guest attributes. This reads them back.
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"
LISTEN_PORT="${LISTEN_PORT:-12359}"
INTERVAL="${INTERVAL:-30}"
MAX_POLLS="${MAX_POLLS:-80}"

ga() {
  gcloud compute instances get-guest-attributes "$INSTANCE_NAME" \
    --project="$PROJECT_ID" --zone="$ZONE" \
    --query-path="judge0-js/$1" --format='value(value)' 2>/dev/null || true
}

IP="$(gcloud compute instances describe "$INSTANCE_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || true)"
printf 'VM %s  ip=%s  port=%s\n' "$INSTANCE_NAME" "${IP:-unknown}" "$LISTEN_PORT"

for i in $(seq 1 "$MAX_POLLS"); do
  status="$(ga status)"
  printf '[%s] poll %-3s status=%s\n' "$(date '+%H:%M:%S')" "$i" "${status:-<none yet>}"

  case "$status" in
    ready)
      echo
      echo "=== node version ==="   ; ga node_version
      echo "=== language 63 ==="    ; ga lang63
      echo "=== languages ==="      ; ga languages
      echo "=== compose ps ==="     ; ga compose_ps
      echo "=== JS stdout ==="      ; ga js_stdout
      echo "=== JS status ==="      ; ga js_status
      echo "=== C/C++/Java/Py ===" ; ga lang_matrix
      echo "=== cgroup fs ==="      ; ga cgroup_fs
      echo "=== disk ==="           ; ga disk_free
      echo
      echo "=== pre-existing containers recorded for rollback ==="
      ga rollback_ps
      ga rollback_compose
      echo
      if [ -n "$IP" ]; then
        echo "=== external check ==="
        curl -fsS -m 20 "http://${IP}:${LISTEN_PORT}/languages" \
          | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))' 2>/dev/null \
          || echo "external port ${LISTEN_PORT} not reachable from here"
      fi
      exit 0
      ;;
    failed_line_*|language_63_missing|js_output_mismatch|missing_language_63)
      echo
      echo "DEPLOY FAILED: $status"
      echo "=== deploy.log tail ==="; ga logtail
      echo "=== docker version ==="; ga docker_version
      echo "=== js_raw ==="   ; ga js_raw
      echo "=== languages ==="; ga languages
      echo "=== compose_ps ==="; ga compose_ps
      echo
      echo "Full log lives at /opt/judge0-js/deploy.log on the VM."
      echo "Pre-existing Judge0 containers were never touched; see rollback_ps above."
      exit 1
      ;;
  esac

  sleep "$INTERVAL"
done

echo "Timed out after $((MAX_POLLS * INTERVAL))s without reaching 'ready'."
exit 1

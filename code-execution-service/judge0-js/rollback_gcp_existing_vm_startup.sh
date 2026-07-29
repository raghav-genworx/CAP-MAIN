#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${PROJECT_ID:-gwx-internship-2026-01}"
ZONE="${ZONE:-us-east1-b}"
INSTANCE_NAME="${INSTANCE_NAME:-gwx-gce-intern-01}"

startup_path="$(mktemp "${TMPDIR:-/tmp}/cap-judge0-original-startup.XXXXXX.sh")"
cat >"$startup_path" <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

systemctl enable --now docker
docker start judge0-server judge0-worker >/dev/null 2>&1 || true

for _ in $(seq 1 60); do
  if docker exec judge0-server bundle exec rails runner \
    'Language.unscoped.find(62).update!(run_cmd: "/usr/bin/java -Xms16m -Xmx128m -XX:+UseSerialGC Main")'; then
    docker restart judge0-worker >/dev/null
    echo "JUDGE0_JAVA_HOTFIX_READY"
    exit 0
  fi
  sleep 5
done

echo "Judge0 Java hotfix failed" >&2
exit 1
SCRIPT

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud compute instances add-metadata "$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --metadata-from-file="startup-script=${startup_path}"
rm -f "$startup_path"

gcloud compute instances reset "$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

printf 'Restored original startup script and reset %s.\n' "$INSTANCE_NAME"

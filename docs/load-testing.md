# Load Testing

CAP includes a guarded asynchronous load harness for the candidate workflow and
evaluation-worker throughput. It uses the same `httpx` dependency as the backend
and emits aggregate measurements only. Session tokens, source code, request
bodies, URLs, and response bodies are never printed.

## Candidate Workflow

Create dedicated test candidates and active session tokens in an isolated test
environment. Copy `candidate-fixtures.example.json` to a file ending in
`.local.json`, populate it, and restrict its permissions:

```bash
cd core-assessment-platform-service
chmod 600 scripts/load/candidate-fixtures.local.json
.venv/bin/python scripts/load/cap_load.py candidate \
  --fixtures scripts/load/candidate-fixtures.local.json \
  --concurrency 20 \
  --iterations 2 \
  --scenarios checkpoint,sample \
  --max-error-rate 0.01 \
  --max-p95-ms 2000
```

Final submission is irreversible for each candidate session. It requires the
explicit `--allow-submit` flag and exactly one iteration:

```bash
.venv/bin/python scripts/load/cap_load.py candidate \
  --fixtures scripts/load/candidate-fixtures.local.json \
  --scenarios checkpoint,submit \
  --iterations 1 \
  --allow-submit
```

## Evaluation Worker

Queue dedicated evaluation jobs first. Supply the internal token through the
environment rather than command history, then run bounded concurrent claims:

```bash
read -r -s CAP_LOAD_INTERNAL_SERVICE_TOKEN
export CAP_LOAD_INTERNAL_SERVICE_TOKEN
.venv/bin/python scripts/load/cap_load.py worker \
  --base-url http://127.0.0.1:8004/api/v1 \
  --concurrency 4 \
  --iterations 10 \
  --batch-size 20 \
  --min-processed 100 \
  --allow-process
```

The command exits with status `2` when error-rate, p95 latency, or processed-job
thresholds fail. Use isolated databases and never run destructive scenarios
against active assessments.

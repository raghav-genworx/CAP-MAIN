# judge0-js — isolated Judge0 with JavaScript (Node.js) support

A self-contained Judge0 deployment supporting **C, C++, Java, Python and
JavaScript (Node.js 22.17.1)**. It runs its own PostgreSQL and Redis and listens
on host port **12359**, so it shares nothing with the existing CAP stack.

Everything here is confined to this folder. No CAP file, container, volume,
database or the root `docker-compose.yml` is read-write touched; the CAP Judge0
config under `../../docker/judge0/` was used as a read-only baseline only.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | Judge0 v1.13.1 on `ruby:2.7.8-slim-bullseye` + gcc/g++/OpenJDK 11/python3 + pinned Node.js 22.17.1 |
| `docker-compose.yml` | server, worker, PostgreSQL, Redis — uniquely named, port 12359 |
| `judge0.conf` | isolated DB/Redis credentials and sandbox limits |
| `languages/active.rb` | active language table, including id 63 |
| `languages/archived.rb` | empty archive list (no ID conflicts) |
| `deploy_gcp_osconfig.sh` | **the** deploy script — targets the existing GCP VM without rebooting it |
| `watch_gcp_judge0_js.sh` | poll deployment status/results from the VM |
| `diag_gcp_judge0_js.sh` | read-only diagnostics via guest attributes (no rebuild) |
| `rollback/` | pre-change snapshots of the VM (see *Rollback*) |

### Superseded scripts — do not run

Three scripts from an earlier attempt are still present and are **footguns**:

| File | Why not |
| --- | --- |
| `deploy_gcp_judge0_js.sh` | can `gcloud compute instances create` a **new VM**, and `instances reset` |
| `deploy_gcp_existing_vm_judge0_js.sh` | `gcloud compute instances reset` — hard power-cycles the VM |
| `rollback_gcp_existing_vm_startup.sh` | `gcloud compute instances reset` |

All three were left in place rather than deleted, since they are not this task's
work product. `deploy_gcp_osconfig.sh` supersedes them and needs no reboot.

## Isolation

| Concern | judge0-js | Existing CAP |
| --- | --- | --- |
| Host port | 12359 | 12358 local / 8080 on the VM |
| Containers | `judge0-js-{server,worker,db,redis}` | `cap-backend-judge0-*` / `judge0-server`, `judge0-worker` |
| Image | `judge0-js-node:local` | `cap/judge0-slim:local` |
| Volumes | `judge0_js_*` | `cap-*`, `cap-platform_*` |
| Compose project | `judge0-js` | `cap-backend`, `cap-frontend` |
| Database / Redis | own containers | CAP's own / external managed instances |

## Local run

```bash
cd judge0-js
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

Verify:

```bash
docker compose ps
docker compose logs judge0-server
curl http://localhost:12359/languages
```

Test JavaScript:

```bash
curl -X POST 'http://localhost:12359/submissions?wait=true' \
  -H 'Content-Type: application/json' \
  -d '{"language_id":63,"source_code":"const fs = require(\"fs\"); console.log(fs.readFileSync(0, \"utf8\").trim());","stdin":"hello javascript"}'
```

## The `judge0.conf` trap

`scripts/load-config` picks `/api/judge0.conf` **in preference to** `/judge0.conf`
and sources it with `set -o allexport`, so that file overrides anything Compose
injects via `environment:` or `env_file:`.

The official `judge0/judge0` image is unaffected because `judge0.conf` is listed
in judge0's `.dockerignore`, so `/api/judge0.conf` never exists in the image and
the conventional `/judge0.conf` mount wins. This Dockerfile installs Judge0 from
the release **tarball**, which does contain `judge0.conf` — so without
intervention the shipped sample defaults (`POSTGRES_HOST=db`,
`POSTGRES_DB=judge0`) silently win and the server crash-loops on
`could not translate host name "db"`.

The Dockerfile therefore does `COPY judge0.conf /api/judge0.conf`, making this
folder's config the authoritative one for the server, the worker, and the cron
jobs that re-source `/api/environment`.

## The cgroup-v1 `memory` controller trap (GCP only)

On the GCP VM every language failed with

```
Internal Error — No such file or directory @ rb_sysopen - /box/script.js
```

That message is misleading. `isolate_job.rb:58` runs

```ruby
@workdir = `isolate #{cgroups} -b #{box_id} --init`.chomp
```

and uses the **stdout** of `isolate --init` as the work directory. When isolate
fails, `@workdir` is `""`, so the source path collapses to `/box/script.js`. The
real error is one level down:

```
Failed to create control group /sys/fs/cgroup/memory/box-0/: No such file or directory
```

isolate 1.8.1 with `--cg` needs the cgroup **v1 memory** controller. The VM runs
kernel 6.17, which gates v1 memcg behind `CONFIG_MEMCG_V1`, so `/sys/fs/cgroup`
contains `blkio cpu cpuacct devices … pids` but **no `memory`**. Docker Desktop
does expose v1 `memory`, which is why this reproduced only on GCP.

`isolate --init` *without* `--cg` succeeds. judge0 drops `--cg` only when both
per-process limit flags are true (`isolate_job.rb:57`), and both default to
false, so `judge0.conf` now sets:

```
ENABLE_PER_PROCESS_AND_THREAD_TIME_LIMIT=true
ENABLE_PER_PROCESS_AND_THREAD_MEMORY_LIMIT=true
```

Trade-off: limits become per-process (isolate `-m` address space, per-process
time) instead of cgroup totals, and reported memory is `max-rss` rather than
`cg-mem`. The existing CAP GCP deployment already ran this way.

The alternative — booting the VM with a kernel that still carries v1 memcg — was
rejected: it needs a reboot and depends on a kernel config we do not control.

### Consequence: `-m` is RLIMIT_AS, so runtimes need virtual headroom

`isolate -m` caps *address space*, not resident memory. Two runtimes reserve far
more virtual memory than they use, so both had to be tuned. Measured on the VM:

| `memory_limit` (KB) | Node 22 (id 63) | plain JVM (id 62) |
| --- | --- | --- |
| 512000 | `Failed to reserve virtual memory for CodeRange` | `Could not reserve … 256000KB object heap` |
| 1000000 | same failure | `… 501760KB object heap` |
| 1500000 | **Accepted** (RSS ~42 MB) | — |
| 2000000 | Accepted | `Could not allocate metaspace: 1073741824 bytes` |

Node needed ≥ 1500000 purely for V8's virtual reservations, hence
`MEMORY_LIMIT=1500000`.

Raising the cap never fixes plain Java, because the JVM sizes heap and metaspace
from **physical** RAM (4 GB here) and simply asks for more as the cap grows.
Language 62 therefore carries explicit `-Xmx`/metaspace/code-cache bounds (and
the same via `-J` for `javac`, which is itself a JVM). That is the durable form
of the runtime hotfix the existing CAP GCP deployment already applies to id 62.

Note the residual risk: with a ~1.4 GB address-space allowance and no cgroup
memory limit, a deliberately allocation-heavy submission can still pressure a
4 GB VM. Wall-clock, CPU and process limits remain in force, but restoring
cgroup v1 memcg (or moving to a judge0/isolate build with cgroup v2 support) is
the real fix if this is exposed to untrusted input.

## GCP deployment

Target: project `gwx-internship-2026-01`, VM `gwx-gce-intern-01`, zone `us-east1-b`.

```bash
./deploy_gcp_osconfig.sh     # apply, no reboot
./watch_gcp_judge0_js.sh     # follow status until "ready"
```

### Why OS Config rather than startup-script + reset

* SSH on `gwx-vpc-intern-01` is IAP-only (`gwx-allow-ssh-iap`, source
  `35.235.240.0/20`) and this principal lacks
  `iap.tunnelInstances.accessViaIAP`, so there is no interactive shell.
* The VM's external IP is **ephemeral** — no reserved address exists — so
  `stop`/`start` would hand out a new IP and break anything pointing at it.
* `instances reset` is a hard power cycle.

An OS Policy Assignment `exec` resource runs an inline script on the *running*
VM: no reboot, no IP change. The script stages files and launches the build via
`systemd-run`, so a slow image build cannot be killed by an agent step timeout.
Progress is reported through **guest attributes** (namespace `judge0-js`), which
is the only readable channel without SSH.

### Safety properties

* Only containers, volumes and networks named `judge0-js*` / `judge0_js*` are
  created or removed.
* `judge0-server` and `judge0-worker` are never stopped, removed or rebuilt.
* Disk is reclaimed with `docker builder prune -af` and `docker image prune -f`
  (dangling only) — never `image prune -a`, which would delete the pre-existing
  Judge0 images that rollback depends on.
* Docker is installed only if absent, and Compose v2 is dropped in as a
  standalone CLI plugin binary, so apt can never decide to remove a `docker-ce`
  engine and take every running container down with it.

## Rollback

`rollback/vm-describe-before.json` and `rollback/serial-before.txt` capture the
VM as it was before any change, and the deploy records live docker state on the
VM at `/opt/judge0-js/rollback/state.txt` plus the `rollback_ps` /
`rollback_compose` guest attributes.

To remove judge0-js from the VM, leaving everything else untouched:

```bash
cd /opt/judge0-js && docker compose down -v
docker rmi judge0-js-node:local
```

Then delete the assignment and the targeting label so it is not re-applied:

```bash
gcloud compute os-config os-policy-assignments delete judge0-js-deploy \
  --project=gwx-internship-2026-01 --location=us-east1-b
gcloud compute instances remove-labels gwx-gce-intern-01 \
  --project=gwx-internship-2026-01 --zone=us-east1-b --labels=judge0-js-deploy
```

## State of the pre-existing VM Judge0 (recorded, not caused by this work)

Before any change here, the VM's Judge0 on port 8080 was **already down**:

* guest attribute `cap-judge0/status` = `readiness_failed`
* TCP 8080 refused, `/languages` unreachable
* serial console: `Error connecting to Redis on redis:6379 (SocketError) /
  Name or service not known`

A previous attempt's `startup-script` had replaced the compose-managed
`judge0-server` / `judge0-worker` with bare `docker run` containers on the
default bridge network. The original stack resolved Redis by the compose service
name `redis`, which does not exist outside that compose network — hence the
SocketError. That same script also remained installed as the VM's
`startup-script`, so **every subsequent boot would re-run `docker rm -f
judge0-server judge0-worker`**.

State actually recorded on the VM by this deployment:

| Guest attribute | Value |
| --- | --- |
| `rollback_ps` | `judge0-server:cap-judge0-slim:js-patched:running`, `judge0-worker:cap-judge0-slim:js-patched:running` |
| `rollback_compose` | `none` (before judge0-js existed) |
| `docker_version` | `29.1.3` (Docker CE, **not** Ubuntu's `docker.io`) |
| `cgroup_fs` | `tmpfs` (cgroup v1, but see the `memory` controller note below) |
| `disk_free` | `27G free of 38G` |

Both `judge0-server` and `judge0-worker` exist and are in `running` state on the
image `cap-judge0-slim:js-patched`, but **port 8080 still serves nothing** — they
restart-loop on the unresolvable `redis` hostname. Neither was touched by this
work; they are in exactly the state the earlier attempt left them.

`rollback_compose` was `none`, i.e. nothing on the VM was compose-managed before
judge0-js, so the original CAP compose project directory is gone.

> Reading guest attributes: multi-line values (`rollback_ps`, `compose_ps`) are
> easy to misread as single-line when piped through `grep`. Query them
> individually with `--query-path` before drawing conclusions.

Because the engine is Docker CE, the deploy script deliberately never runs
`apt-get install docker.io` unconditionally: apt would resolve that by *removing*
`docker-ce`, tearing down every running container on the VM.

This is recorded rather than silently repaired. Restoring the original CAP Judge0
is a separate decision from adding JS support, and it now needs its compose
project (or equivalent `docker run` invocation with a reachable Redis)
reconstructed — the recorded env in `/opt/judge0-js/rollback/state.txt` and
`rollback/vm-describe-before.json` is the starting point.

### Verified deployment result

Confirmed against `http://34.73.165.69:12359` after deployment, with the VM never
rebooted (`lastStartTimestamp` unchanged) and its IP unchanged:

```
id 50   C (GCC)                Accepted   c-ok
id 54   C++ (G++)              Accepted   cpp-ok
id 62   Java (OpenJDK)         Accepted   java-ok
id 1003 Java (CAP bounded)     Accepted   java-cap-ok
id 71   Python (3)             Accepted   py-ok
id 63   JavaScript (Node.js)   Accepted   js-ok
id 63   JavaScript + stdin     Accepted   hello javascript
id 63   JavaScript multiline   Accepted   10
```

`node_version = v22.17.1`, `cgroups_mode = per-process (max-rss)`, all four
containers `running`.

### Leftover project-level change

Enabling the no-reboot path required two project-scoped settings. Revert with:

```bash
gcloud compute os-config project-feature-settings update \
  --project=gwx-internship-2026-01 --patch-and-config-feature-set=limited
gcloud compute project-info remove-metadata \
  --project=gwx-internship-2026-01 --keys=enable-osconfig
```

Reverting these blocks future OS Config deploys but does not affect the running
judge0-js stack.

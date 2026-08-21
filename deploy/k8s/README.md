# Deploying Market Agent M1 on Rancher Desktop (local k3s)

Deploys the FastAPI backend, an in-cluster PostgreSQL, an Alembic migration
Job, and the Flutter web UI onto a local Rancher Desktop Kubernetes cluster.
No registry or CI is involved -- images are built and loaded locally.

## Prerequisites

- Rancher Desktop running, Kubernetes enabled (ships with Traefik as the
  default ingress controller and a `local-path` default StorageClass).
- `kubectl` and `docker` on PATH and pointed at the Rancher Desktop context
  (`kubectl config current-context` should show `rancher-desktop`).
- `nerdctl` available (bundled with Rancher Desktop) -- used to load locally
  built images into the cluster's containerd, regardless of which container
  engine mode (dockerd/moby or containerd) Rancher Desktop is set to.

## 1. Configure secrets

```powershell
Copy-Item deploy/k8s/market-agent.env.example deploy/k8s/market-agent.env
notepad deploy/k8s/market-agent.env   # fill in real values
```

`deploy/k8s/market-agent.env` is gitignored. It is the **only** place real
credentials are written -- never paste them into a manifest, script, or this
README. Leave `OPENAI_API_KEY` / `UPSTOX_ACCESS_TOKEN` blank to run without
that provider.

## 2. Build and deploy -- one command

```powershell
./deploy/k8s/deploy.ps1
```

`deploy.ps1` builds both images, best-effort loads them into the cluster's
containerd via `nerdctl` (only meaningful in Rancher Desktop's containerd
engine mode -- in dockerd/moby mode this step harmlessly no-ops because k3s
already shares the same Docker image store `docker build` populates),
applies the base manifests, (re)creates the `market-agent-secrets` Secret
from `market-agent.env`, waits for Postgres, runs the Alembic migration Job,
and restarts the API/web Deployments. It's safe to re-run.

For a redeploy where no new Alembic revision shipped, skip the migration
step: `./deploy/k8s/deploy.ps1 -SkipMigrate`.

Doing it by hand instead (what the script automates), in order:

```powershell
docker build -t market-agent-api:local .
docker build --build-arg API_BASE_URL=http://market-agent.test -t market-agent-web:local flutter_app
docker save market-agent-api:local | nerdctl --namespace k8s.io load
docker save market-agent-web:local | nerdctl --namespace k8s.io load
kubectl apply -k deploy/k8s/base
kubectl create secret generic market-agent-secrets -n market-agent --from-env-file=deploy/k8s/market-agent.env --dry-run=client -o yaml | kubectl apply -f -
kubectl -n market-agent rollout status deploy/postgres
kubectl apply -f deploy/k8s/base/migration-job.yaml
kubectl -n market-agent wait --for=condition=complete job/market-agent-migrate --timeout=120s
kubectl -n market-agent rollout restart deploy/market-agent-api deploy/market-agent-web
```

The API/web pods will crash-loop until the Secret exists and Postgres is
ready -- expected, and self-heals once both are in place.

## 3. Point the hostname at the cluster

The Ingress host is `market-agent.test` (deliberately **not** `*.localhost`:
Chromium-based browsers hardcode the entire `.localhost` TLD to `127.0.0.1`
and ignore the hosts file for it, which breaks routing to Traefik's real
address). Add an entry to `C:\Windows\System32\drivers\etc\hosts` (as
Administrator) pointing at Traefik's LoadBalancer IP:

```powershell
kubectl get svc -n kube-system traefik   # note the EXTERNAL-IP
Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" -Value "`n<EXTERNAL-IP> market-agent.test"
```

That IP can change if the Rancher Desktop VM is recreated -- if
`market-agent.test` stops resolving correctly, re-check the Traefik
EXTERNAL-IP and update the hosts entry.

## 4. Verify

```powershell
Invoke-WebRequest http://market-agent.test/health
Invoke-WebRequest http://market-agent.test/api/models
```

Open `http://market-agent.test/` in a browser for the Flutter UI.

```powershell
kubectl -n market-agent get pods
kubectl -n market-agent logs job/market-agent-migrate
```

All pods should be `Running`/`Completed` with no `ImagePullBackOff` or
`CrashLoopBackOff`.

## 5. Ingest market data and run the discovery scan (EPIC-M1.150)

A freshly deployed cluster's PostgreSQL starts empty, so `/api/v1/discoveries`
and the Flutter Discover screen are honestly empty until you run these --
same idea as the root README's Docker Compose `ingest`/`discovery` section,
just as Kubernetes Jobs instead of `docker compose run`.

```powershell
# 1. Load NSE candles from whichever provider MARKET_DATA_PROVIDER selects in
#    market-agent.env (default yahoo). Edit ingest-job.yaml's FROM_DATE/TO_DATE
#    env values first if you want a different window than the default.
kubectl -n market-agent delete job/market-agent-ingest --ignore-not-found
kubectl apply -f deploy/k8s/base/ingest-job.yaml
kubectl -n market-agent wait --for=condition=complete job/market-agent-ingest --timeout=180s
kubectl -n market-agent logs job/market-agent-ingest

# 2. Turn that market data into real scan_candidates + discovery_records
kubectl -n market-agent delete job/market-agent-discovery --ignore-not-found
kubectl apply -f deploy/k8s/base/discovery-job.yaml
kubectl -n market-agent wait --for=condition=complete job/market-agent-discovery --timeout=120s
kubectl -n market-agent logs job/market-agent-discovery
```

Or do both as part of a deploy: `./deploy/k8s/deploy.ps1 -RunIngest -RunDiscovery`.

Both Jobs are on-demand and are **not** applied by `kubectl apply -k
deploy/k8s/base` (same reasoning as `migration-job.yaml`: a Job's spec is
immutable once created, so re-running means delete-then-reapply, shown
above). Re-running either is safe -- both scripts are idempotent for the
same input window/date; see `scripts/ingest_market_history.py` and
`scripts/run_discovery_scan.py`.

For a standing cluster you don't want to babysit, `deploy/k8s/base/discovery-cronjob.yaml`
(applied automatically as part of the base kustomization) runs the same
discovery scan daily at 10:30 UTC / 16:00 IST on weekdays. It still depends on
`market-agent-ingest` having populated fresh market data first -- the
CronJob only scans, it never ingests.

Once discovery has run, `GET /api/v1/discoveries` (and the Flutter Discover
screen served by `web`) reflect the persisted records directly through the
Traefik ingress -- no separate backend step.

## Teardown

```powershell
kubectl delete -k deploy/k8s/base
```

The Postgres PVC is **not** deleted by this (data persists across
teardown/redeploy). To wipe it: `kubectl delete pvc postgres-data -n market-agent`.

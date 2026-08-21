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
docker build --build-arg API_BASE_URL=http://market-agent.localhost -t market-agent-web:local flutter_app
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

## 3. Verify

```powershell
Invoke-WebRequest http://market-agent.localhost/health
Invoke-WebRequest http://market-agent.localhost/api/models
```

Open `http://market-agent.localhost/` in a browser for the Flutter UI.
`.localhost` resolves to `127.0.0.1` in modern browsers/OSes with no
`/etc/hosts` edit needed.

```powershell
kubectl -n market-agent get pods
kubectl -n market-agent logs job/market-agent-migrate
```

All pods should be `Running`/`Completed` with no `ImagePullBackOff` or
`CrashLoopBackOff`.

## Teardown

```powershell
kubectl delete -k deploy/k8s/base
```

The Postgres PVC is **not** deleted by this (data persists across
teardown/redeploy). To wipe it: `kubectl delete pvc postgres-data -n market-agent`.

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

## 2. Build images

```powershell
docker build -t market-agent-api:local .
docker build --build-arg API_BASE_URL=http://market-agent.localhost -t market-agent-web:local flutter_app
```

## 3. Load images into the cluster

```powershell
docker save market-agent-api:local | nerdctl --namespace k8s.io load
docker save market-agent-web:local | nerdctl --namespace k8s.io load
```

## 4. Apply base manifests

```powershell
kubectl apply -k deploy/k8s/base
```

This creates the `market-agent` namespace, Postgres, the API/web Deployments,
Services, and the Ingress. The API and web pods will crash-loop until the
Secret exists (next step) and Postgres is ready -- expected, and self-heals.

## 5. Create the Secret

```powershell
kubectl create secret generic market-agent-secrets `
  -n market-agent --from-env-file=deploy/k8s/market-agent.env
```

## 6. Wait for Postgres, then run migrations

```powershell
kubectl -n market-agent rollout status deploy/postgres
kubectl apply -f deploy/k8s/base/migration-job.yaml
kubectl -n market-agent wait --for=condition=complete job/market-agent-migrate --timeout=120s
```

## 7. Restart API/web to pick up the Secret

```powershell
kubectl -n market-agent rollout restart deploy/market-agent-api deploy/market-agent-web
```

## 8. Verify

```powershell
curl http://market-agent.localhost/health
curl http://market-agent.localhost/api/models
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

## Redeploying after code changes

```powershell
docker build -t market-agent-api:local .   # or the web build command above
docker save market-agent-api:local | nerdctl --namespace k8s.io load
kubectl -n market-agent rollout restart deploy/market-agent-api
```

If a new Alembic revision shipped, re-run migrations first:

```powershell
kubectl -n market-agent delete job/market-agent-migrate --ignore-not-found
kubectl apply -f deploy/k8s/base/migration-job.yaml
kubectl -n market-agent wait --for=condition=complete job/market-agent-migrate --timeout=120s
```

## Teardown

```powershell
kubectl delete -k deploy/k8s/base
```

The Postgres PVC is **not** deleted by this (data persists across
teardown/redeploy). To wipe it: `kubectl delete pvc postgres-data -n market-agent`.

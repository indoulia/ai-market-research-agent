<#
.SYNOPSIS
  Build both images and deploy the Market Agent stack to Rancher Desktop (k3s)
  in one command.
.EXAMPLE
  ./deploy/k8s/deploy.ps1
.EXAMPLE
  ./deploy/k8s/deploy.ps1 -SkipMigrate    # redeploy without re-running Alembic
#>
[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "http://market-agent.test",
    [string]$Namespace = "market-agent",
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$EnvFile = Join-Path $PSScriptRoot "market-agent.env"
$BaseDir = Join-Path $PSScriptRoot "base"
$MigrationJob = Join-Path $BaseDir "migration-job.yaml"

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$Description, [Parameter(Mandatory)][ScriptBlock]$Command)
    Write-Host "==> $Description" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Failed: $Description (exit code $LASTEXITCODE)"
    }
}

# Only needed when Rancher Desktop's container engine is set to containerd.
# In dockerd (moby) mode, k3s already shares the same Docker image store
# that `docker build` populates, so nerdctl has nothing to bridge and
# reliably errors ("cannot access containerd socket") -- harmless there.
function Invoke-BestEffort {
    param([Parameter(Mandatory)][string]$Description, [Parameter(Mandatory)][ScriptBlock]$Command)
    Write-Host "==> $Description" -ForegroundColor Cyan
    & $Command 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    (skipped/failed -- fine under dockerd engine mode; image is already usable)" -ForegroundColor DarkYellow
    }
}

if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile. Copy market-agent.env.example to market-agent.env and fill in real values first."
}

Push-Location $RepoRoot
try {
    Invoke-Checked "Build API image" { docker build -t market-agent-api:local . }
    Invoke-Checked "Build web image" { docker build --build-arg API_BASE_URL=$ApiBaseUrl -t market-agent-web:local flutter_app }

    Invoke-BestEffort "Load API image into cluster containerd (containerd engine mode only)" { docker save market-agent-api:local | nerdctl --namespace k8s.io load }
    Invoke-BestEffort "Load web image into cluster containerd (containerd engine mode only)" { docker save market-agent-web:local | nerdctl --namespace k8s.io load }

    Invoke-Checked "Apply base manifests" { kubectl apply -k $BaseDir }

    Invoke-Checked "Create/update market-agent-secrets Secret" {
        kubectl create secret generic market-agent-secrets -n $Namespace --from-env-file=$EnvFile --dry-run=client -o yaml | kubectl apply -f -
    }

    Invoke-Checked "Wait for Postgres" { kubectl -n $Namespace rollout status deploy/postgres --timeout=120s }

    if (-not $SkipMigrate) {
        Invoke-Checked "Re-run Alembic migration job" {
            kubectl -n $Namespace delete job/market-agent-migrate --ignore-not-found
            kubectl apply -f $MigrationJob
            kubectl -n $Namespace wait --for=condition=complete job/market-agent-migrate --timeout=120s
        }
    }

    Invoke-Checked "Restart API/web deployments" {
        kubectl -n $Namespace rollout restart deploy/market-agent-api deploy/market-agent-web
        kubectl -n $Namespace rollout status deploy/market-agent-api --timeout=120s
        kubectl -n $Namespace rollout status deploy/market-agent-web --timeout=120s
    }

    Write-Host "==> Verifying" -ForegroundColor Cyan
    $health = Invoke-WebRequest -UseBasicParsing -Uri "$ApiBaseUrl/health"
    Write-Host $health.Content
    Write-Host "Deployed. Open $ApiBaseUrl in a browser." -ForegroundColor Green
}
finally {
    Pop-Location
}

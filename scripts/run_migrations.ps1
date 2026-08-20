$ErrorActionPreference = "Stop"
if (-not (Test-Path ".env")) {
    Write-Error ".env not found. Copy .env.example to .env and configure DATABASE_URL."
}
alembic upgrade head

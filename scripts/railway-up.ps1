# CLI deploy from your PC. Uploads LOCAL files — sync with Origin/GitHub first if health still shows v2.
# Must link the storykeep WEB service in production, NOT the Postgres plugin.

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".git")) {
    Write-Error "Run this from the Storykeep repo root (folder with Dockerfile)."
}

Write-Host "Linking project (pick Storykeep project -> production -> storykeep WEB service, NOT Postgres)..."
railway link

Write-Host "Current linked service:"
railway status

$confirm = Read-Host "Deploy to the service above? (y/N)"
if ($confirm -notmatch '^[Yy]') {
    Write-Host "Cancelled."
    exit 0
}

Write-Host "Uploading and building..."
railway up

Write-Host ""
Write-Host "If deploy shows CRASHED, open Railway -> storykeep -> Deployments -> failed deploy -> Deploy Logs."
Write-Host "Verify: https://storykeep-production.up.railway.app/api/health"

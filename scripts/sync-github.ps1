# Push latest Storykeep from Cursor Origin to GitHub so Railway GitHub deploys pick it up.
# Run in PowerShell from your Storykeep folder (e.g. C:\Users\steve\Storykeep).

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".git")) {
    Write-Error "Run this from the Storykeep repo root (folder with Dockerfile)."
}

Write-Host "Fetching latest from Cursor Origin..."
git fetch origin
git merge origin/main --no-edit

Write-Host "Pushing to GitHub (sb11b/Storykeep-)..."
git push github main

Write-Host ""
Write-Host "Done. In Railway: open the storykeep WEB service (not Postgres) -> Deployments -> Redeploy."
Write-Host "Verify build stamp: https://storykeep-production.up.railway.app/api/health"
Write-Host "  Expect build >= junior-cursor-delegate-v3 (or newer junior-* stamp)."

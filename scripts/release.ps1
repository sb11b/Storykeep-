<#
.SYNOPSIS
    Releases a new StoryKeep desktop version: bump, tag, build, sign, publish.

.DESCRIPTION
    PowerShell-primary release script for the StoryKeep Tauri v2 desktop app.
    The updater is click-to-install: users get the new version through the
    in-app banner, which reads the `latest.json` this script publishes to
    GitHub Releases.

    Steps (each one fails loudly — the script stops at the first error and
    prints what it did):

      1.  Preflight: clean tree, not already tagged, on `main`, gh + git present.
      2.  Bump the version in frontend/src-tauri/tauri.conf.json,
          frontend/src-tauri/Cargo.toml and frontend/package.json.
      3.  Commit ("chore(release): v<version>"), annotated tag "v<version>",
          push both to origin.
      4.  Build the NSIS + MSI bundles with updater signing
          (`createUpdaterArtifacts: true` in tauri.conf.json makes
          `tauri build` sign and emit .sig files next to the installers).
      5.  Generate latest.json (windows-aarch64 platform key — the app is
          built for Windows ARM64 only).
      6.  `gh release create v<version>` with the installers, their .sig
          files and latest.json.

    Signing key: the minisign private key must exist somewhere safe
    (password manager). Point the script at it ONE of these ways:

      - `$env:STORYKEEP_UPDATE_KEY = "C:\keys\storykeep-update.key"`
        (a path OR the key content itself — the Tauri CLI accepts both),
      - or `$env:TAURI_SIGNING_PRIVATE_KEY` already set in your session.

    The key has no passphrase, so `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
    is set to "" automatically.

.EXAMPLE
    .\scripts\release.ps1 0.1.1
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoSlug = 'sb11b/Storykeep-'
$Tag = "v$Version"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $RepoRoot 'frontend'
$TauriDir = Join-Path $Frontend 'src-tauri'
$TauriConf = Join-Path $TauriDir 'tauri.conf.json'
$CargoToml = Join-Path $TauriDir 'Cargo.toml'
$PackageJson = Join-Path $Frontend 'package.json'

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    throw "release.ps1: $Message"
}

function Invoke-Git {
    param([string[]]$Arguments)
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "git $($Arguments -join ' ') failed:`n$output"
    }
    return ($output | Out-String).Trim()
}

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
Write-Step "Preflight checks for StoryKeep $Tag"

foreach ($tool in @('git', 'gh')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "'$tool' is not on PATH — install it first."
    }
}

$branch = Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')
if ($branch -ne 'main') {
    Fail "releases ship from 'main' (on '$branch'). Merge the release PR first, then re-run."
}

$porcelain = Invoke-Git @('status', '--porcelain')
if ($porcelain) {
    Fail "working tree is dirty — commit or stash first:`n$porcelain"
}

$existingTag = Invoke-Git @('tag', '--list', $Tag)
if ($existingTag) {
    Fail "tag $Tag already exists locally."
}

$remoteTag = & git ls-remote --tags origin "refs/tags/$Tag" 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "could not query origin for tag $Tag:`n$remoteTag"
}
if ($remoteTag) {
    Fail "tag $Tag already exists on origin."
}

# The signing key: path or content, per the Tauri CLI (see .SYNOPSIS).
$signingKey = $env:STORYKEEP_UPDATE_KEY
if (-not $signingKey) { $signingKey = $env:TAURI_SIGNING_PRIVATE_KEY }
if (-not $signingKey) {
    Fail @"
no signing key configured. The minisign private key lives in your password
manager (or a safe file). Set ONE of:

    `$env:STORYKEEP_UPDATE_KEY = "C:\path\to\storykeep-update.key"
    `$env:TAURI_SIGNING_PRIVATE_KEY = "C:\path\to\storykeep-update.key"

Both accept the key CONTENT as well as the path. Never commit the private key.
"@
}

Write-Host "  branch: $branch (clean, untagged)"

# ---------------------------------------------------------------------------
# 2. Bump the version
# ---------------------------------------------------------------------------
Write-Step "Bumping version to $Version"

# Replaces the FIRST top-level "version" value in each file (exactly one
# match is expected; anything else is a malformed manifest).
function Set-VersionInFile {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "$Label not found at $Path"
    }
    $content = Get-Content -LiteralPath $Path -Raw
    $matches = [regex]::Matches($content, $Pattern)
    if ($matches.Count -ne 1) {
        Fail "$Label at $Path has $($matches.Count) 'version' entries — expected exactly 1."
    }
    $updated = [regex]::Replace(
        $content,
        $Pattern,
        { param($m) $m.Groups[1].Value + '"' + $Version + '"' },
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    # .NET writes UTF-8 without a BOM — a BOM would corrupt tauri.conf.json.
    [System.IO.File]::WriteAllText($Path, $updated)
    Write-Host "  $Label -> $Version"
}

Set-VersionInFile -Path $TauriConf -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'tauri.conf.json'
Set-VersionInFile -Path $CargoToml -Pattern '(?m)^(version\s*=\s*)"[^"]*"' -Label 'Cargo.toml'
Set-VersionInFile -Path $PackageJson -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'package.json'

# Guard against a no-op bump (same version as before) — the commit below
# would fail with a confusing "nothing to commit".
$currentTauriVersion = (Get-Content -LiteralPath $TauriConf -Raw | ConvertFrom-Json).version
if ($currentTauriVersion -ne $Version) {
    Fail "tauri.conf.json did not take the new version (still $currentTauriVersion)."
}

# ---------------------------------------------------------------------------
# 3. Commit, tag, push
# ---------------------------------------------------------------------------
Write-Step "Committing and tagging $Tag"

Invoke-Git @('add', '--', $TauriConf, $CargoToml, $PackageJson)
Invoke-Git @('commit', '-m', "chore(release): v$Version")
Invoke-Git @('tag', '-a', $Tag, '-m', "StoryKeep $Tag")

Write-Step "Pushing to origin"
Invoke-Git @('push', 'origin', 'main')
Invoke-Git @('push', 'origin', "refs/tags/$Tag")
Write-Host "  pushed commit + tag $Tag"

# ---------------------------------------------------------------------------
# 4. Build with signing
# ---------------------------------------------------------------------------
Write-Step "Building bundles (NSIS + MSI) with updater signing"

if (-not (Test-Path -LiteralPath (Join-Path $Frontend 'node_modules'))) {
    Write-Host "  node_modules missing — running npm ci first"
    Push-Location $Frontend
    try { npm ci } finally { Pop-Location }
}

$env:TAURI_SIGNING_PRIVATE_KEY = $signingKey
# The key has no passphrase — the empty string is what makes the build
# non-interactive. (An empty value is not the same as unset for the CLI.)
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ''

Push-Location $Frontend
try {
    # `tauri build` runs beforeBuildCommand (the Next.js static export)
    # and, thanks to createUpdaterArtifacts, signs every bundle and writes
    # a matching .sig next to each installer.
    npm run tauri:build
    if ($LASTEXITCODE -ne 0) {
        Fail "npm run tauri:build failed (exit $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}

$BundleRoot = Join-Path $TauriDir 'target\release\bundle'
$msi = Get-ChildItem -Path (Join-Path $BundleRoot 'msi') -Filter *.msi -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $msi) {
    Fail "no MSI bundle found under $BundleRoot\msi."
}
$msiSig = "$($msi.FullName).sig"
if (-not (Test-Path -LiteralPath $msiSig)) {
    Fail @"
updater signature missing: $msiSig
`tauri build` did not sign the MSI. Check that tauri.conf.json has
"bundle": { "createUpdaterArtifacts": true } and that TAURI_SIGNING_PRIVATE_KEY
points at the right key.
"@
}
Write-Host "  MSI:   $($msi.Name)"
Write-Host "  .sig:  $(Split-Path -Leaf $msiSig)"

$nsis = Get-ChildItem -Path (Join-Path $BundleRoot 'nsis') -Filter *.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1

# ---------------------------------------------------------------------------
# 5. Generate latest.json (the update manifest)
# ---------------------------------------------------------------------------
Write-Step "Generating latest.json (windows-aarch64)"

$pubDate = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$signature = (Get-Content -LiteralPath $msiSig -Raw).Trim()
$msiUrl = "https://github.com/$RepoSlug/releases/download/$Tag/$($msi.Name)"

# Same shape as buildLatestJson() in frontend/src/lib/auto-update.ts — the
# updater expects { version, notes, pub_date, platforms: { "<os>-<arch>":
# { signature, url } } }. PSCustomObject (not [ordered]@{}) because
# ConvertTo-Json preserves property order reliably on PowerShell 5.1.
$latest = [pscustomobject]@{
    version = $Version
    notes = "https://github.com/$RepoSlug/releases/tag/$Tag"
    pub_date = $pubDate
    platforms = [pscustomobject]@{
        'windows-aarch64' = [pscustomobject]@{
            signature = $signature
            url = $msiUrl
        }
    }
}
$latestJson = $latest | ConvertTo-Json -Depth 10
$latestPath = Join-Path $BundleRoot 'latest.json'
# WriteAllText (UTF-8, NO BOM): Set-Content -Encoding utf8 on PS 5.1 emits
# a BOM, which would make the manifest invalid JSON to the updater.
[System.IO.File]::WriteAllText($latestPath, $latestJson)
Write-Host "  $latestPath"
Write-Host $latestJson

# ---------------------------------------------------------------------------
# 6. Publish the GitHub Release
# ---------------------------------------------------------------------------
Write-Step "Creating GitHub release $Tag"

$assets = @($msi.FullName, $msiSig, $latestPath)
if ($nsis) {
    $assets += $nsis.FullName
    $nsisSig = "$($nsis.FullName).sig"
    if (Test-Path -LiteralPath $nsisSig) { $assets += $nsisSig }
}

& gh release create $Tag @assets --repo $RepoSlug --title "StoryKeep $Tag" --generate-notes
if ($LASTEXITCODE -ne 0) {
    Fail "gh release create failed. The tag is pushed but the release is not — fix and re-run just the release step: gh release create $Tag <assets> --repo $RepoSlug --title ""StoryKeep $Tag"" --generate-notes"
}

Write-Step "Done — StoryKeep $Tag released"
Write-Host "  release: https://github.com/$RepoSlug/releases/tag/$Tag"
Write-Host "  users on an older version get the click-to-install banner on next launch."

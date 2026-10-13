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
          frontend/src-tauri/Cargo.toml, frontend/package.json and
          frontend/package-lock.json.
      3.  Commit ("chore(release): v<version>"), annotated tag "v<version>",
          push both to origin.
      4.  Build the NSIS + MSI bundles with updater signing
          (`createUpdaterArtifacts: true` in tauri.conf.json makes
          `tauri build` sign and emit .sig files next to the installers).
      5.  Generate latest.json (windows-aarch64 platform key — the app is
          built for Windows ARM64 only). The manifest points at the NSIS
          bundle: the updater cannot cross installer formats, and NSIS is
          the format users install from. The MSI ships as an alternative
          manual download only.
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
$PackageLock = Join-Path $Frontend 'package-lock.json'

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
    Fail "could not query origin for tag ${Tag}:`n$remoteTag"
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

# Bump the two root version mirrors in package-lock.json: the top-level
# "version" and packages[""].version. Parsed as JSON so the ~700 nested
# per-package "version" keys are never touched.
function Set-VersionInPackageLock {
    param(
        [string]$Path,
        [string]$Version
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "package-lock.json not found at $Path"
    }
    $lock = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if (-not $lock.PSObject.Properties['packages'] -or
        -not $lock.packages.PSObject.Properties['']) {
        Fail "package-lock.json at $Path has no packages[\"\"] entry — unsupported lockfile shape."
    }
    $lock.version = $Version
    $lock.packages.''.version = $Version
    $json = $lock | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($Path, $json)
    Write-Host "  package-lock.json (root + packages[\"\"]) -> $Version"
}

Set-VersionInFile -Path $TauriConf -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'tauri.conf.json'
Set-VersionInFile -Path $CargoToml -Pattern '(?m)^(version\s*=\s*)"[^"]*"' -Label 'Cargo.toml'
Set-VersionInFile -Path $PackageJson -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'package.json'
# package-lock.json carries its own "version" mirroring package.json in TWO
# places: the top-level key and packages[""].version. npm ci validates
# package.json against the lockfile — a mismatch aborts the install the
# build depends on. It CANNOT go through Set-VersionInFile: the file has
# ~700 nested "version" keys, so the regex's exactly-one-match guard would
# abort. Edit the two known spots as parsed JSON instead (key order and
# formatting preserved by ConvertTo-Json at the same depth; the lockfile is
# machine-generated anyway).
Set-VersionInPackageLock -Path $PackageLock -Version $Version

# Guard against a no-op bump (same version as before) — the commit below
# would fail with a confusing "nothing to commit".
$currentTauriVersion = (Get-Content -LiteralPath $TauriConf -Raw | ConvertFrom-Json).version
if ($currentTauriVersion -ne $Version) {
    Fail "tauri.conf.json did not take the new version (still $currentTauriVersion)."
}
$currentLockVersion = (Get-Content -LiteralPath $PackageLock -Raw | ConvertFrom-Json).version
if ($currentLockVersion -ne $Version) {
    Fail "package-lock.json did not take the new version (still $currentLockVersion)."
}

# ---------------------------------------------------------------------------
# 3. Commit, tag, push
# ---------------------------------------------------------------------------
Write-Step "Committing and tagging $Tag"

Invoke-Git @('add', '--', $TauriConf, $CargoToml, $PackageJson, $PackageLock)
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
    # Native commands don't trip $ErrorActionPreference='Stop' — check the
    # exit code explicitly or a failed npm ci would fall through to the
    # build with a stale/partial node_modules.
    if ($LASTEXITCODE -ne 0) {
        Fail "npm ci failed (exit $LASTEXITCODE)."
    }
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
    Fail ('updater signature missing: ' + $msiSig + ' - tauri build did not sign the MSI. Check that tauri.conf.json has bundle.createUpdaterArtifacts enabled and TAURI_SIGNING_PRIVATE_KEY points at the right key.')
}
Write-Host "  MSI:   $($msi.Name)"
Write-Host "  .sig:  $(Split-Path -Leaf $msiSig)"

# The updater must hand users the SAME installer format they already have:
# Tauri has no cross-format update path (an NSIS install cannot be updated
# by an MSI payload). Steve's existing install is the NSIS setup.exe, so
# latest.json points at the NSIS bundle and its signature — the MSI stays
# in the release as an alternative manual download only, never as the
# update payload. If the installed base ever switches to MSI, flip this
# one block (and reinstall from MSI on the affected machines).
$nsisBundle = Get-ChildItem -Path (Join-Path $BundleRoot 'nsis') -Filter *.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $nsisBundle) {
    Fail "no NSIS bundle found under $BundleRoot\nsis — latest.json must point at the same format users install from."
}
$nsisSig = "$($nsisBundle.FullName).sig"
if (-not (Test-Path -LiteralPath $nsisSig)) {
    Fail ('updater signature missing: ' + $nsisSig + ' - tauri build did not sign the NSIS bundle. Check that tauri.conf.json has bundle.createUpdaterArtifacts enabled and TAURI_SIGNING_PRIVATE_KEY points at the right key.')
}
Write-Step "Generating latest.json (windows-aarch64)"

$pubDate = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$signature = (Get-Content -LiteralPath $nsisSig -Raw).Trim()
$nsisUrl = "https://github.com/$RepoSlug/releases/download/$Tag/$($nsisBundle.Name)"

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
            url = $nsisUrl
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

# Both installers go up as manual downloads; latest.json (the update
# payload) points at the NSIS bundle only. Both .sig files are uploaded so
# a future MSI-based update path needs no rebuild.
$assets = @($msi.FullName, $msiSig, $nsisBundle.FullName, $nsisSig, $latestPath)

& gh release create $Tag @assets --repo $RepoSlug --title "StoryKeep $Tag" --generate-notes
if ($LASTEXITCODE -ne 0) {
    Fail ('gh release create failed. The tag is pushed but the release is not — fix the error and re-run just the release step: gh release create ' + $Tag + ' --repo ' + $RepoSlug + ' --title ''StoryKeep ' + $Tag + ''' --generate-notes')
}

Write-Step "Done — StoryKeep $Tag released"
Write-Host "  release: https://github.com/$RepoSlug/releases/tag/$Tag"
Write-Host "  users on an older version get the click-to-install banner on next launch."

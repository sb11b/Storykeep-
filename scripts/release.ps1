<#
.SYNOPSIS
    Releases a new StoryKeep desktop version: bump, tag, build, sign, publish.

.DESCRIPTION
    PowerShell-primary release script for the StoryKeep Tauri v2 desktop app.
    The updater is click-to-install: users get the new version through the
    in-app banner, which reads the `latest.json` this script publishes to
    GitHub Releases.

    Steps (each one fails loudly -- the script stops at the first error and
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
      5.  Generate latest.json (windows-aarch64 platform key -- the app is
          built for Windows ARM64 only). The manifest points at the NSIS
          bundle: the updater cannot cross installer formats, and NSIS is
          the format users install from. The MSI ships as an alternative
          manual download only.
      6.  `gh release create v<version>` with the installers, their .sig
          files and latest.json.

    Signing key: the minisign private key must exist somewhere safe
    (password manager). Point the script at it ONE of these ways:

      - `$env:STORYKEEP_UPDATE_KEY = "C:\keys\storykeep-update.key"`
        (a path OR the key content itself -- the Tauri CLI accepts both),
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
    # Native commands (git) write progress to STDERR and exit 0 on success.
    # Under $ErrorActionPreference='Stop', PowerShell 5.1 promotes that stderr
    # to a terminating NativeCommandError -- so a SUCCESSFUL push would throw
    # and abort the release. Drop to 'Continue' for the call so stderr is just
    # captured text; the exit code is the real success signal, checked below.
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & git @Arguments 2>&1
    } finally {
        $ErrorActionPreference = $oldEAP
    }
    if ($LASTEXITCODE -ne 0) {
        Fail "git $($Arguments -join ' ') failed:`n$($output | Out-String)"
    }
    return ($output | Out-String).Trim()
}

# Echo a native command's captured output (stdout+stderr merged) line by line.
# Forces array semantics with @() so a single-line result is not iterated as
# characters, and stringifies ErrorRecords (native stderr) explicitly -- under
# Set-StrictMode, PS 5.1's formatter reads .InvocationInfo.Statement on a
# native ErrorRecord (which is $null) and aborts with "property 'Statement'
# cannot be found" if such a record reaches the pipeline/formatter directly.
function Write-NativeOutput {
    param($Output)
    foreach ($line in @($Output)) {
        if ($line -is [System.Management.Automation.ErrorRecord]) {
            Write-Host $line.ToString()
        } elseif ($null -ne $line) {
            Write-Host $line
        }
    }
}

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
Write-Step "Preflight checks for StoryKeep $Tag"

foreach ($tool in @('git', 'gh')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "'$tool' is not on PATH -- install it first."
    }
}

$branch = Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')
if ($branch -ne 'main') {
    Fail "releases ship from 'main' (on '$branch'). Merge the release PR first, then re-run."
}

$porcelain = Invoke-Git @('status', '--porcelain')
if ($porcelain) {
    Fail "working tree is dirty -- commit or stash first:`n$porcelain"
}

$existingTag = Invoke-Git @('tag', '--list', $Tag)
if ($existingTag) {
    Fail "tag $Tag already exists locally."
}

$oldEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $remoteTag = & git ls-remote --tags origin "refs/tags/$Tag" 2>&1
} finally {
    $ErrorActionPreference = $oldEAP
}
if ($LASTEXITCODE -ne 0) {
    Fail "could not query origin for tag ${Tag}:`n$($remoteTag | Out-String)"
}
if ($remoteTag) {
    Fail "tag $Tag already exists on origin."
}

# The signing key: path or content, per the Tauri CLI (see .SYNOPSIS).
$signingKey = $env:STORYKEEP_UPDATE_KEY
if (-not $signingKey) { $signingKey = $env:TAURI_SIGNING_PRIVATE_KEY }
if (-not $signingKey) {
    $signingKeyHelp = @"
no signing key configured. The minisign private key lives in your password
manager (or a safe file). Set ONE of:

    `$env:STORYKEEP_UPDATE_KEY = "C:\path\to\storykeep-update.key"
    `$env:TAURI_SIGNING_PRIVATE_KEY = "C:\path\to\storykeep-update.key"

Both accept the key CONTENT as well as the path. Never commit the private key.
"@
    Fail $signingKeyHelp
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
        Fail "$Label at $Path has $($matches.Count) 'version' entries -- expected exactly 1."
    }
    $updated = [regex]::Replace(
        $content,
        $Pattern,
        { param($m) $m.Groups[1].Value + '"' + $Version + '"' },
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    # .NET writes UTF-8 without a BOM -- a BOM would corrupt tauri.conf.json.
    [System.IO.File]::WriteAllText($Path, $updated)
    Write-Host "  $Label -> $Version"
}

# Bump the two root version mirrors in package-lock.json: the top-level
# "version" and packages[""].version. npm lockfileVersion 3 stores an
# empty-string key packages[""], and Windows PowerShell 5.1 ConvertFrom-Json
# cannot build a property named "" (it throws "value of argument name is not
# valid"). So we never round-trip through a PSCustomObject: edit the two known
# version mirrors as text. Each is the ONLY "version" at its position (the
# top-level one precedes the packages block; the packages[""] one is the first
# "version" after the "": { marker), so a scoped single-match replace is exact
# and never touches the ~700 nested per-package version keys.
function Set-VersionInPackageLock {
    param(
        [string]$Path,
        [string]$Version
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "package-lock.json not found at $Path"
    }
    $raw = [System.IO.File]::ReadAllText($Path)
    $rootMarker = '"packages": {'
    $rootIdx = $raw.IndexOf($rootMarker)
    if ($rootIdx -lt 0) {
        Fail "package-lock.json at $Path has no packages block -- unsupported lockfile shape."
    }
    $emptyKeyIdx = $raw.IndexOf('"": {', $rootIdx)
    if ($emptyKeyIdx -lt 0) {
        Fail "package-lock.json at $Path has no packages[""] entry -- unsupported lockfile shape."
    }
    # Replace only the FIRST "version" match in a given slice, by index, so the
    # ~700 nested per-package version keys are never touched. [regex]::Replace
    # with a count argument does not limit matches in PowerShell, so we match
    # once and splice by index instead.
    $versionRe = '(?m)^([ ]*"version"[ ]*:[ ]*)"[^"]*"'
    # 1) top-level mirror: the first "version" before the packages block.
    $head = $raw.Substring(0, $rootIdx)
    $hm = [regex]::Match($head, $versionRe)
    if (-not $hm.Success) {
        Fail "package-lock.json at $Path has no top-level version -- unsupported lockfile shape."
    }
    $headNew = $head.Substring(0, $hm.Index) + $hm.Groups[1].Value + '"' + $Version + '"' + $head.Substring($hm.Index + $hm.Length)
    # 2) packages[""] mirror: the first "version" after the "": { marker.
    $tail = $raw.Substring($emptyKeyIdx)
    $tm = [regex]::Match($tail, $versionRe)
    if (-not $tm.Success) {
        Fail "package-lock.json at $Path has no packages[""] version -- unsupported lockfile shape."
    }
    $tailNew = $tail.Substring(0, $tm.Index) + $tm.Groups[1].Value + '"' + $Version + '"' + $tail.Substring($tm.Index + $tm.Length)
    $middle = $raw.Substring($rootIdx, $emptyKeyIdx - $rootIdx)
    $newRaw = $headNew + $middle + $tailNew
    [System.IO.File]::WriteAllText($Path, $newRaw)
    Write-Host "  package-lock.json (root + packages[""]) -> $Version"
}

Set-VersionInFile -Path $TauriConf -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'tauri.conf.json'
Set-VersionInFile -Path $CargoToml -Pattern '(?m)^(version\s*=\s*)"[^"]*"' -Label 'Cargo.toml'
Set-VersionInFile -Path $PackageJson -Pattern '(?m)^(\s*"version"\s*:\s*)"[^"]*"' -Label 'package.json'
Set-VersionInPackageLock -Path $PackageLock -Version $Version

# Guard against a no-op bump (same version as before) -- the commit below
# would fail with a confusing "nothing to commit".
$currentTauriVersion = (Get-Content -LiteralPath $TauriConf -Raw | ConvertFrom-Json).version
if ($currentTauriVersion -ne $Version) {
    Fail "tauri.conf.json did not take the new version (still $currentTauriVersion)."
}
# Read the lockfile version as text (ConvertFrom-Json would throw on the
# empty-string key under PS 5.1). The first "version" in the file is the
# top-level mirror we just wrote.
$lockText = [System.IO.File]::ReadAllText($PackageLock)
$lockMatch = [regex]::Match($lockText, '(?m)^[ ]*"version"[ ]*:[ ]*"([^"]*)"')
$currentLockVersion = $lockMatch.Groups[1].Value
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
    Write-Host "  node_modules missing -- running npm ci first"
    Push-Location $Frontend
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $ciOutput = $null
    try {
        $ciOutput = & npm ci 2>&1
        Write-NativeOutput $ciOutput
    } finally {
        $ErrorActionPreference = $oldEAP
        Pop-Location
    }
    # Native commands don't trip $ErrorActionPreference='Stop' -- check the
    # exit code explicitly or a failed npm ci would fall through to the
    # build with a stale/partial node_modules.
    if ($LASTEXITCODE -ne 0) {
        Fail "npm ci failed (exit $LASTEXITCODE).`n$($ciOutput | Out-String)"
    }
}

$env:TAURI_SIGNING_PRIVATE_KEY = $signingKey
# The key has no passphrase -- the empty string is what makes the build
# non-interactive. (An empty value is not the same as unset for the CLI.)
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ''

Push-Location $Frontend
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$buildOutput = $null
try {
    # `tauri build` runs beforeBuildCommand (the Next.js static export)
    # and, thanks to createUpdaterArtifacts, signs every bundle and writes
    # a matching .sig next to each installer.
    # Capture merged stdout+stderr into a variable, then echo only the
    # string lines. Piping native stderr straight to Out-Host under
    # Set-StrictMode makes PS 5.1's error formatter read .InvocationInfo
    # .Statement on a native ErrorRecord (which is $null) and abort with
    # "property 'Statement' cannot be found". Writing strings avoids that.
    $buildOutput = & npm run tauri:build 2>&1
    Write-NativeOutput $buildOutput
} finally {
    $ErrorActionPreference = $oldEAP
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    Fail "npm run tauri:build failed (exit $LASTEXITCODE).`n$($buildOutput | Out-String)"
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
# latest.json points at the NSIS bundle and its signature -- the MSI stays
# in the release as an alternative manual download only, never as the
# update payload. If the installed base ever switches to MSI, flip this
# one block (and reinstall from MSI on the affected machines).
$nsisBundle = Get-ChildItem -Path (Join-Path $BundleRoot 'nsis') -Filter *.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $nsisBundle) {
    Fail "no NSIS bundle found under $BundleRoot\nsis -- latest.json must point at the same format users install from."
}
$nsisSig = "$($nsisBundle.FullName).sig"
if (-not (Test-Path -LiteralPath $nsisSig)) {
    Fail ('updater signature missing: ' + $nsisSig + ' - tauri build did not sign the NSIS bundle. Check that tauri.conf.json has bundle.createUpdaterArtifacts enabled and TAURI_SIGNING_PRIVATE_KEY points at the right key.')
}
Write-Step "Generating latest.json (windows-aarch64)"

$pubDate = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$signature = (Get-Content -LiteralPath $nsisSig -Raw).Trim()
$nsisUrl = "https://github.com/$RepoSlug/releases/download/$Tag/$($nsisBundle.Name)"

# Same shape as buildLatestJson() in frontend/src/lib/auto-update.ts -- the
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

$oldEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$ghOutput = $null
try {
    $ghOutput = & gh release create $Tag @assets --repo $RepoSlug --title "StoryKeep $Tag" --generate-notes 2>&1
    Write-NativeOutput $ghOutput
} finally {
    $ErrorActionPreference = $oldEAP
}
if ($LASTEXITCODE -ne 0) {
    Fail ('gh release create failed (exit ' + $LASTEXITCODE + '). The tag is pushed but the release is not. Fix the error, then re-run just the release step: gh release create TAG ASSETS --repo sb11b/Storykeep- --title StoryKeep TAG --generate-notes (substitute TAG and the asset paths).`n' + ($ghOutput | Out-String))
}

Write-Step "Done - StoryKeep $Tag released"
Write-Host "  release: https://github.com/$RepoSlug/releases/tag/$Tag"
Write-Host "  users on an older version get the click-to-install banner on next launch."

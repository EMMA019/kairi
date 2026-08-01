#Requires -Version 5.1
<#
.SYNOPSIS
  Build BOOTH Windows zip (frontend/dist + backend/app + launcher + optional embedded Python).
  Does NOT ship settings.json, *.db, .env, tests, or evals.

.PARAMETER SkipEmbed
  Do not bundle runtime/python (buyers need system Python). For quick smoke builds only.

.PARAMETER PrepareEmbed
  Run prepare_embedded_python.ps1 before packaging (default: use existing runtime if present).
#>
param(
  [switch]$SkipEmbed,
  [switch]$PrepareEmbed,
  [switch]$ForceEmbedRebuild
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Stage = Join-Path $Root "dist\booth\Kairi"
$ZipOut = Join-Path $Root "dist\booth\Kairi-BOOTH.zip"
$RuntimeSrc = Join-Path $Root "runtime\python"

Write-Host "==> Root: $Root"

if (-not $SkipEmbed) {
  $needPrepare = $PrepareEmbed -or $ForceEmbedRebuild -or -not (Test-Path (Join-Path $RuntimeSrc "python.exe"))
  if ($needPrepare) {
    Write-Host "==> Preparing embedded Python"
    $prepArgs = @("-File", (Join-Path $PSScriptRoot "prepare_embedded_python.ps1"))
    if ($ForceEmbedRebuild) { $prepArgs += "-Force" }
    & powershell -NoProfile -ExecutionPolicy Bypass @prepArgs
    if ($LASTEXITCODE -ne 0) { throw "prepare_embedded_python.ps1 failed" }
  } elseif (-not (Test-Path (Join-Path $RuntimeSrc ".kairi_deps_ok"))) {
    Write-Host "==> runtime/python exists but deps marker missing; preparing..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "prepare_embedded_python.ps1")
    if ($LASTEXITCODE -ne 0) { throw "prepare_embedded_python.ps1 failed" }
  } else {
    Write-Host "==> Using existing embedded Python: $RuntimeSrc"
  }
} else {
  Write-Host "==> SkipEmbed: zip will require system Python"
}

$Frontend = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
  throw "frontend/package.json not found"
}
Push-Location $Frontend
try {
  if (-not (Test-Path "node_modules")) {
    Write-Host "==> npm ci"
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
  }
  Write-Host "==> npm run build"
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
  Pop-Location
}

$DistIndex = Join-Path $Frontend "dist\index.html"
if (-not (Test-Path $DistIndex)) {
  throw "frontend/dist/index.html missing after build"
}

if (Test-Path $Stage) {
  Remove-Item -Recurse -Force $Stage
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

function Copy-TreeFiltered {
  param(
    [string]$Src,
    [string]$Dst,
    [string[]]$ExcludeDirNames = @(),
    [string[]]$ExcludeFilePatterns = @()
  )
  New-Item -ItemType Directory -Path $Dst -Force | Out-Null
  Get-ChildItem -Path $Src -Force | ForEach-Object {
    $name = $_.Name
    if ($_.PSIsContainer) {
      if ($ExcludeDirNames -contains $name) { return }
      Copy-TreeFiltered -Src $_.FullName -Dst (Join-Path $Dst $name) `
        -ExcludeDirNames $ExcludeDirNames -ExcludeFilePatterns $ExcludeFilePatterns
    } else {
      foreach ($pat in $ExcludeFilePatterns) {
        if ($name -like $pat) { return }
      }
      Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Dst $name) -Force
    }
  }
}

Write-Host "==> Copy backend/app"
Copy-TreeFiltered `
  -Src (Join-Path $Root "backend\app") `
  -Dst (Join-Path $Stage "backend\app") `
  -ExcludeDirNames @("__pycache__", ".pytest_cache", "tests") `
  -ExcludeFilePatterns @("*.pyc", "*.pyo", "*.db")

Get-ChildItem -Path (Join-Path $Stage "backend\app") -Recurse -Filter "*.db" -ErrorAction SilentlyContinue |
  Remove-Item -Force

Write-Host "==> Copy requirements + storage example"
New-Item -ItemType Directory -Path (Join-Path $Stage "backend\storage") -Force | Out-Null
Copy-Item (Join-Path $Root "backend\requirements.txt") (Join-Path $Stage "backend\requirements.txt") -Force
$Example = Join-Path $Root "backend\storage\settings.example.json"
if (-not (Test-Path $Example)) { throw "settings.example.json missing" }
Copy-Item $Example (Join-Path $Stage "backend\storage\settings.example.json") -Force

foreach ($d in @("backend\storage\briefings", "backend\cache", "backend\storage\search_cache")) {
  $dirPath = Join-Path $Stage $d
  New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
  Set-Content -Path (Join-Path $dirPath ".gitkeep") -Value ""
}

Write-Host "==> Copy frontend/dist"
Copy-Item -Recurse (Join-Path $Frontend "dist") (Join-Path $Stage "frontend\dist") -Force

Write-Host "==> Copy launcher + docs"
Copy-Item (Join-Path $Root "kairi_desktop.py") (Join-Path $Stage "kairi_desktop.py") -Force
Copy-Item (Join-Path $Root "start_kairi.bat") (Join-Path $Stage "start_kairi.bat") -Force

$BoothDocs = Join-Path $Root "booth"
if (Test-Path $BoothDocs) {
  Get-ChildItem -LiteralPath $BoothDocs -File | Where-Object {
    $_.Extension -in @(".txt", ".md")
  } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Stage $_.Name) -Force
    Write-Host ("Copied doc: " + $_.Name)
  }
} else {
  Write-Warning "booth/ docs folder missing"
}

if (-not $SkipEmbed) {
  if (-not (Test-Path (Join-Path $RuntimeSrc "python.exe"))) {
    throw "Embedded Python missing at $RuntimeSrc (run prepare_embedded_python.ps1)"
  }
  Write-Host "==> Copy runtime/python (this may take a minute)"
  Copy-TreeFiltered `
    -Src $RuntimeSrc `
    -Dst (Join-Path $Stage "runtime\python") `
    -ExcludeDirNames @("__pycache__") `
    -ExcludeFilePatterns @("*.pyc", "*.pyo")
}

$Forbidden = @(
  "backend\storage\settings.json",
  "backend\.env",
  ".env"
)
foreach ($rel in $Forbidden) {
  $p = Join-Path $Stage $rel
  if (Test-Path $p) {
    Remove-Item -Force $p
    Write-Host "Removed forbidden: $rel"
  }
}
Get-ChildItem -Path $Stage -Recurse -ErrorAction SilentlyContinue |
  Where-Object {
    -not $_.PSIsContainer -and (
      $_.Extension -eq ".db" -or
      $_.Name -eq ".env" -or
      ($_.Name -eq "settings.json")
    )
  } |
  ForEach-Object {
    Write-Host "Removed: $($_.FullName)"
    Remove-Item -Force $_.FullName
  }

Write-Host "==> Zip"
if (Test-Path $ZipOut) { Remove-Item -Force $ZipOut }
$ZipParent = Split-Path $ZipOut -Parent
if (-not (Test-Path $ZipParent)) { New-Item -ItemType Directory -Path $ZipParent -Force | Out-Null }
Compress-Archive -Path $Stage -DestinationPath $ZipOut -Force

Write-Host ""
Write-Host "OK: $ZipOut"
Write-Host "Stage: $Stage"
$embedNote = if ($SkipEmbed) { "NO embedded Python" } else { "WITH embedded Python" }
Write-Host "Packaging: $embedNote"
Get-Item $ZipOut | Format-List Name, Length, LastWriteTime

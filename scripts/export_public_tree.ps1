# Export a clean worktree for a squash public repo (no private git history).
# Usage (from repo root):
#   powershell -File scripts/export_public_tree.ps1 -OutDir ..\kairi-public
#
# Then:
#   cd ..\kairi-public
#   git init
#   git add .
#   git commit -m "Initial public release"
#   gh repo create OWNER/kairi --public --source=. --remote=origin --push

param(
    [Parameter(Mandatory = $true)]
    [string]$OutDir
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Dest = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir)

if (Test-Path $Dest) {
    throw "OutDir already exists: $Dest"
}

New-Item -ItemType Directory -Path $Dest | Out-Null

# Prefer git archive so .gitignore (booth/, storage/, etc.) is honored.
Push-Location $Root
try {
    $archive = Join-Path $env:TEMP ("kairi-public-{0}.tar" -f [guid]::NewGuid().ToString("n"))
    git archive --format=tar HEAD -o $archive
    if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
        throw "tar is required to extract git archive on Windows (Win10+ usually has it)."
    }
    tar -xf $archive -C $Dest
    Remove-Item $archive -Force
} finally {
    Pop-Location
}

# Defense in depth: drop paths that must never ship publicly even if tracked again.
$never = @(
    "booth",
    "storage",
    "gyaru_dash",
    "scratch",
    "openresty",
    "services",
    ".wrangler",
    "front",
    "test_guidance_hallucination.py",
    "to_md.py",
    "backend\storage\violation_logs",
    "backend\storage\projects.json",
    "backend\storage\settings.json",
    "backend\storage\kv_store.json",
    "qiita_kairi_article.md",
    "SECURITY_AUDIT_REPORT.md"
)
foreach ($rel in $never) {
    $p = Join-Path $Dest $rel
    if (Test-Path $p) {
        Remove-Item -Recurse -Force $p
        Write-Host "removed $rel"
    }
}

# Ensure example env is present
$envExample = Join-Path $Dest ".env.example"
if (-not (Test-Path $envExample)) {
    Write-Warning ".env.example missing from archive — check git tracking."
}

Write-Host ""
Write-Host "Export ready: $Dest"
Write-Host "Next:"
Write-Host "  cd `"$Dest`""
Write-Host "  git init"
Write-Host "  git add ."
Write-Host "  git commit -m `"Initial public release`""
Write-Host "  # create empty public repo, then:"
Write-Host "  git remote add origin https://github.com/OWNER/REPO.git"
Write-Host "  git push -u origin HEAD:main"

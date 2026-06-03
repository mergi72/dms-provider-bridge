param(
    [string]$OutputDir = "artifacts"
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot

try {
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Write-Error "Git was not found in PATH."
        exit 1
    }

    $shortSha = (git rev-parse --short HEAD).Trim()
    if (-not $shortSha) {
        Write-Error "Unable to determine HEAD commit."
        exit 1
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null

    $zipPath = Join-Path $OutputDir "edocat-bridge-$shortSha-$timestamp.zip"
    git archive --format=zip --output="$zipPath" HEAD

    Write-Host "Release ZIP created: $zipPath"
    Write-Host "Archive contains tracked files only (no __pycache__, .pyc, or local logs)."
}
finally {
    Pop-Location
}

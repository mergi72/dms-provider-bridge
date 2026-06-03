$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot

try {
    $cacheDirs = Get-ChildItem -Path . -Recurse -Force -Directory -Filter "__pycache__"
    $pycFiles = Get-ChildItem -Path . -Recurse -Force -File -Filter "*.pyc"
    $pyoFiles = Get-ChildItem -Path . -Recurse -Force -File -Filter "*.pyo"

    foreach ($dir in $cacheDirs) {
        Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    foreach ($file in ($pycFiles + $pyoFiles)) {
        Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
    }

    $logPath = Join-Path $repoRoot "edocat_requests.log"
    if (Test-Path $logPath) {
        Remove-Item -Path $logPath -Force -ErrorAction SilentlyContinue
        Write-Host "Removed log: edocat_requests.log"
    }

    Write-Host "Removed __pycache__ dirs: $($cacheDirs.Count)"
    Write-Host "Removed bytecode files: $($pycFiles.Count + $pyoFiles.Count)"
}
finally {
    Pop-Location
}

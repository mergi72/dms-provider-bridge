$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot

try {
    $excludedRoots = @(".git", ".venv", ".venv312", ".pytest_cache", ".tmp", "artifacts", "build", "dist")
    $searchRoots = Get-ChildItem -Path . -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $excludedRoots -notcontains $_.Name }

    $cacheDirs = @($searchRoots | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
    })
    $pycFiles = @($searchRoots | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue
    })
    $pyoFiles = @($searchRoots | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File -Filter "*.pyo" -ErrorAction SilentlyContinue
    })

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

param(
    [ValidateSet("unit", "integration", "all")]
    [string]$Suite = "all"
)

$pythonCandidates = @(
    ".\.venv312\Scripts\python.exe",
    ".\.venv\Scripts\python.exe"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $python = $pythonCmd.Source
    }
}

if (-not (Test-Path $python)) {
    Write-Error "Python interpreter not found. Tried .venv312, .venv and PATH python."
    exit 1
}

switch ($Suite) {
    "unit" {
        & $python -m pytest -q -m unit
        exit $LASTEXITCODE
    }
    "integration" {
        & $python -m pytest -q -m integration
        exit $LASTEXITCODE
    }
    "all" {
        & $python -m pytest -q
        exit $LASTEXITCODE
    }
}

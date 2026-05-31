param(
    [ValidateSet("unit", "integration", "all")]
    [string]$Suite = "all"
)

$python = ".\.venv312\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Python interpreter not found at $python"
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

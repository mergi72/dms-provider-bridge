#!/usr/bin/env bash
set -euo pipefail

suite="${1:-all}"
python_bin=".venv312/Scripts/python.exe"

if [ ! -f "$python_bin" ]; then
  echo "Python interpreter not found at $python_bin" >&2
  exit 1
fi

case "$suite" in
  unit)
    "$python_bin" -m pytest -q -m unit
    ;;
  integration)
    "$python_bin" -m pytest -q -m integration
    ;;
  all)
    "$python_bin" -m pytest -q
    ;;
  *)
    echo "Usage: ./scripts/run-tests.sh [unit|integration|all]" >&2
    exit 2
    ;;
esac

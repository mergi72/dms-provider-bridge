#!/usr/bin/env bash
set -euo pipefail

suite="${1:-all}"
python_bin=""

for candidate in \
  ".venv312/Scripts/python.exe" \
  ".venv/Scripts/python.exe" \
  ".venv312/bin/python" \
  ".venv/bin/python"
do
  if [ -f "$candidate" ]; then
    python_bin="$candidate"
    break
  fi
done

if [ -z "$python_bin" ] && command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
fi

if [ -z "$python_bin" ] && command -v python >/dev/null 2>&1; then
  python_bin="python"
fi

if [ -z "$python_bin" ]; then
  echo "Python interpreter not found. Tried .venv312, .venv and PATH python3/python." >&2
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

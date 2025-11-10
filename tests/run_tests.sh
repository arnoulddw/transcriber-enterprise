#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/app"
cd "${PROJECT_ROOT}"

export PYTHONPATH="${PYTHONPATH:-/app}"

echo ">>> Installing dev dependencies..."
pip install --user -r requirements-dev.txt >/tmp/pip-dev-install.log
tail -n +1 /tmp/pip-dev-install.log

echo ">>> Running pytest..."
exec /app/.local/bin/pytest "$@"

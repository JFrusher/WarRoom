#!/usr/bin/env bash
# Run every component's unit suite. Requires the dev dependencies:
#   pip install flask requests beautifulsoup4 flask-socketio pytest
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"

for suite in \
    "agent_core" \
    "services/target_app" \
    "services/referee" \
    "agents/red_team" \
    "agents/blue_team" \
    "dashboard"; do
    echo "== pytest ${suite} =="
    (cd "${ROOT}/${suite}" && "${PYTHON}" -m pytest tests/ -q)
done

echo "== end-to-end smoke =="
"${PYTHON}" "${ROOT}/tests/e2e_smoke.py"

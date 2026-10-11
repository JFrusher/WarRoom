#!/usr/bin/env bash
# Run every component's unit suite. Requires the dev dependencies:
#   pip install flask requests beautifulsoup4 flask-socketio pytest
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for suite in \
    "services/target_app" \
    "agents/red_team" \
    "agents/blue_team" \
    "dashboard"; do
    echo "== pytest ${suite} =="
    (cd "${ROOT}/${suite}" && python -m pytest tests/ -q)
done

echo "== end-to-end smoke =="
python "${ROOT}/tests/e2e_smoke.py"

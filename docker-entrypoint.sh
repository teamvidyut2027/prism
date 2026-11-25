#!/bin/sh
# "serve" (default): build the benchmark if it is missing, then start the dashboard.
# Anything else is executed as given, e.g. `python -m prism reproduce` or `python -m pytest -q`.
set -e
if [ "$1" = "serve" ]; then
  if [ ! -f data/datasets/prism-core/dataset.json ]; then
    echo "[prism] first start: building prism-core (about 1 minute)..."
    python -m prism build --name prism-core --per-cell 8
    python -m prism eval --dataset prism-core --model oracle:pixels >/dev/null
    python -m prism eval --dataset prism-core --model baseline:prior >/dev/null
    python -m prism eval --dataset prism-core --model baseline:random >/dev/null
  fi
  exec python -m prism serve --host "${PRISM_HOST:-0.0.0.0}" --port "${PRISM_PORT:-8000}"
fi
exec "$@"

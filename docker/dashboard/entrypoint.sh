#!/bin/sh
set -eu

echo "[dashboard] Starting Streamlit dashboard"
echo "[dashboard] Python: $(python --version 2>&1)"

python - <<'PY'
from pathlib import Path
import streamlit

app_path = Path("/app/dashboard/app.py")
client_path = Path("/app/dashboard/snapshot_client.py")

print(f"[dashboard] Streamlit: {streamlit.__version__}", flush=True)
print(f"[dashboard] app.py exists: {app_path.is_file()}", flush=True)
print(
    f"[dashboard] snapshot_client.py exists: {client_path.is_file()}",
    flush=True,
)

if not app_path.is_file():
    raise SystemExit("[dashboard] Missing /app/dashboard/app.py")

if not client_path.is_file():
    raise SystemExit(
        "[dashboard] Missing /app/dashboard/snapshot_client.py"
    )
PY

if [ -z "${PUBLIC_SNAPSHOT_BASE_URL:-}" ]; then
    echo "[dashboard] ERROR: PUBLIC_SNAPSHOT_BASE_URL is empty" >&2
    exit 1
fi

echo "[dashboard] Snapshot URL is configured"
echo "[dashboard] Listening on 0.0.0.0:8501"

exec /usr/local/bin/streamlit run /app/dashboard/app.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    --logger.level=info

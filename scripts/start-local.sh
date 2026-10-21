#!/usr/bin/env bash
set -eo pipefail
source "$(dirname "$0")/persistent-env.sh"
PY="$SMARTCOURSE_RUNTIME_ROOT/venv/bin/python"
test -x "$PY" || { echo 'Run scripts/setup-local.sh first.' >&2; exit 1; }
mkdir -p "$REPO_ROOT/ui-adapter/.preview"
"$PY" -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"base_url":"http://127.0.0.1:18771"}))' "$REPO_ROOT/ui-adapter/.preview/service.json"
"$PY" -m app.server --host 127.0.0.1 --port 18771 >>"$SMARTCOURSE_RUNTIME_ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!
"$PY" "$REPO_ROOT/ui-adapter/serve.py" --port 18772 >>"$SMARTCOURSE_RUNTIME_ROOT/logs/adapter.log" 2>&1 &
ADAPTER_PID=$!
printf 'Backend PID: %s; adapter PID: %s
' "$BACKEND_PID" "$ADAPTER_PID"
cd "$REPO_ROOT/vue-app"
exec npm run dev

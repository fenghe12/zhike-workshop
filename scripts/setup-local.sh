#!/usr/bin/env bash
set -eo pipefail
source "$(dirname "$0")/persistent-env.sh"
"${PYTHON:-python3}" -m venv "$SMARTCOURSE_RUNTIME_ROOT/venv"
"$SMARTCOURSE_RUNTIME_ROOT/venv/bin/python" -m pip install -r "$REPO_ROOT/requirements/backend-local.txt"
cd "$REPO_ROOT/vue-app"
npm ci

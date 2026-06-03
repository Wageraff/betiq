#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
echo "API → http://0.0.0.0:8001/docs"
nohup "$PY" -m app.api >> logs/api.log 2>&1 &
echo "PID: $!"

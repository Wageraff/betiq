#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
"$PY" -m app.url_loader "${1:-urls.txt}"

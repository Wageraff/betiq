#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
LIMIT_ARG=""; INPUT_ARG=""
[ -n "$1" ] && LIMIT_ARG="--limit $1"
[ -n "$2" ] && INPUT_ARG="--input $2"
echo "BetIQ parser → logs/parser.log"
nohup "$PY" -m app.scraper $LIMIT_ARG $INPUT_ARG >> logs/parser.log 2>&1 &
echo "PID: $!"
echo "tail -f logs/parser.log"

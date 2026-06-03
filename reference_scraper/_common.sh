# Общие настройки для run-скриптов (source из bash-файлов).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "❌ venv не найден: $PY"
    echo "   Сначала запусти установку: bash install.sh"
    exit 1
fi

cd "$ROOT"

"""Загрузка и сохранение списков URL."""
from pathlib import Path


def load_urls(path: str | Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url = line.split("#", 1)[0].strip()
            if url:
                urls.append(url)
    return list(dict.fromkeys(urls))


def save_failed_urls(path: str | Path, entries: list[tuple[str, str | None]]):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Неудачные URL — скопируй в urls.txt или: ./venv/bin/python -m app.scraper --input failed_urls.txt\n\n")
        for url, error in entries:
            if error:
                f.write(f"{url}  # {error[:120]}\n")
            else:
                f.write(f"{url}\n")

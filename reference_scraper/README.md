# BetIQ Parser

Парсер страниц с прогнозами — **на основе [bwb-parser](../bwb-parser)**.

Собирает: `title`, `h1`, `meta`, `content_html`, `source` (домен).  
Без iframe — для BetIQ важен текст прогноза и метаданные.

## Структура

```
betiq/
├── config.ini       ← настройки, селекторы
├── urls.txt         ← список URL
├── proxies.txt      ← прокси (не в git)
├── core.txt         ← маркетинговая стратегия BetIQ
├── app/
│   ├── scraper.py   ← Playwright + прокси
│   ├── database.py  ← SQLite (pages + queue)
│   ├── api.py       ← REST API :8001
│   └── ...
└── data/pages.db
```

## Быстрый старт

```bash
bash install.sh
# настрой config.ini, proxies.txt, urls.txt
./venv/bin/python -m app.scraper --limit 5
bash run_results.sh
bash run_api.sh   # http://IP:8001/docs
```

## Отличия от bwb-parser

| bwb-parser | betiq |
|------------|-------|
| Слоты Bigwinboard | Прогнозы / статьи БК-сайтов |
| `slots` + iframe | `pages` + контент |
| locale en-GB | locale ru-RU |
| API :8000 | API :8001 |
| iframe обязателен | контент ≥ 200 символов |

## Фоновый запуск

```bash
bash run_parser.sh
```

## Повтор failed

```bash
./venv/bin/python -m app.scraper --input failed_urls.txt
```

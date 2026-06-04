# Шаблоны промптов для AI

## AI-сводка по матчу

| Файл | Назначение |
|------|------------|
| `ai_match_summary.txt` | Промпт для `src.ai.summarizer` |

Путь задаётся в `config.ini`:

```ini
[ai]
prompt_template = prompts/ai_match_summary.txt
```

Можно указать свой файл (относительно корня проекта `/opt/betiq` или абсолютный путь).

## Переменные в шаблоне

Синтаксис: `{{имя_переменной}}` — подставляется при генерации сводки.

| Переменная | Содержимое |
|------------|------------|
| `{{team_home}}` | Домашняя команда / соперник 1 |
| `{{team_away}}` | Гостевая команда / соперник 2 |
| `{{match_title}}` | `team_home vs team_away` |
| `{{match_date}}` | Дата и время начала (UTC, ISO) |
| `{{competition}}` | Турнир / лига |
| `{{sport}}` | Вид спорта (`football`, `tennis`, …) |
| `{{predictions_count}}` | Число прогнозов на матч |
| `{{predictions_block}}` | Текстовый блок: источник, язык, ставки с коэффициентами, фрагмент анализа |
| `{{slug}}` | Slug матча в API |

Блок `{{predictions_block}}` формируется автоматически, пример:

```text
Source: legalbet.ru (ru)
Bets: П1 @ 1.85, ТБ 2.5 @ 1.90
Analysis: ...
---
Source: beturi.ro (ro)
...
```

После правки шаблона перезапуск scheduler не обязателен — файл читается при каждом вызове summarizer.

Проверка промпта без вызова API:

```bash
./venv/bin/python3.11 -m src.ai.summarizer --match-id 49 --print-prompt
```

# ТЗ: Агрегатор спортивных прогнозов — Backend Data Pipeline

> **Версия:** 2.0  
> **Для кого:** Задание для Cursor AI  
> **Что это:** Сервис сбора, хранения и AI-обработки спортивных прогнозов с множества источников. Без фронтенда. Данные отдаются по REST API внешним SEO-сайтам.

---

## 1. Концепция системы

```
[Источники на RO/EN/RU/...] 
        ↓ парсинг по расписанию
[PostgreSQL: matches + predictions + bets]
        ↓ если 2+ прогнозов на матч
[Claude API → ai_summary на English]
        ↓
[REST API] → SEO-сайты забирают данные и переводят сами
        ↓
[Telegram Bot] — алерты, управление источниками
```

---

## 2. Технический стек

**Важно:** В папке проекта уже есть рабочий парсер на Python (`/reference_scraper/`). Cursor **обязан изучить его перед написанием любого кода** и использовать проверенные решения оттуда (см. раздел 2а).

Стек нового проекта строится на Python, чтобы переиспользовать паттерны из reference-парсера:

- **Runtime:** Python 3.11+
- **API Framework:** FastAPI + Uvicorn
- **БД:** PostgreSQL
- **ORM:** SQLAlchemy 2.0 (async) + Alembic (миграции)
- **Парсер:** Playwright (async) + playwright-stealth + BeautifulSoup4
- **Планировщик:** APScheduler (AsyncIOScheduler)
- **AI:** Anthropic Claude API (`claude-sonnet-4-20250514`)
- **Telegram Bot:** python-telegram-bot (v20+, async)
- **Деплой:** Docker Compose

---

## 2а. Обязательное изучение reference-парсера

**Перед написанием любого кода** Cursor должен открыть и прочитать все файлы в папке `/reference_scraper/`. Там находится боевой парсер на Python, который уже решил большинство технических проблем. Ниже — конкретные решения, которые нужно взять оттуда.

### Что брать из каких файлов

#### `proxy_pool.py` → взять целиком как `src/scraper/proxy_pool.py`
Класс `ProxyPool` — готовое решение для работы с прокси:
- Round-robin ротация со случайным offset (`self._idx`)
- Временный бан сломанного прокси на `BAN_SECONDS=300` секунд (`report_failure`)
- Thread-safe через `threading.Lock()`
- `to_playwright(proxy)` — конвертация строки прокси в формат Playwright (`{"server": ..., "username": ..., "password": ...}`)
- `_mask(proxy)` — маскировка пароля в логах
- Загрузка из `proxies.txt` — по одному адресу на строку, формат `http://user:pass@host:port`

#### `scraper.py` → взять паттерны запуска браузера
Функция `scrape_one()` содержит проверенный способ запуска Playwright с обходом Cloudflare:
```python
launch_args = {
    "headless": HEADLESS,
    "args": [
        "--disable-blink-features=AutomationControlled",  # ключевой флаг
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
}
# После создания page — всегда применять stealth:
if HAS_STEALTH:
    await stealth_async(page)

# После page.goto() — обязательная пауза для Cloudflare:
await page.wait_for_timeout(random.randint(2000, 4000))
```

Ротация User-Agent из `settings.py` — список из 5 реальных UA (`USER_AGENTS`), выбирать через `random.choice()`.

Контекст браузера всегда создаётся с:
```python
context = await browser.new_context(
    user_agent=user_agent,
    viewport={"width": 1366, "height": 768},
    locale="en-US",
    timezone_id="Europe/London",
    ignore_https_errors=True,
)
```

#### `scraper.py` → паттерн retry с детектом прокси-ошибок
```python
_PROXY_ERRORS = ("ERR_CERT", "ERR_CONNECTION", "ERR_PROXY", "ERR_TUNNEL", "net::")

for attempt in range(2):
    try:
        data = await scrape_one(...)
        break
    except Exception as e:
        if any(x in str(e) for x in _PROXY_ERRORS):
            proxy_pool.report_failure(proxy)  # банить только при прокси-ошибке
        mark_failed(url, str(e))
```

#### `diagnose.py` → взять как `src/scraper/diagnose.py`
Утилита для проверки: может ли парсер пройти Cloudflare на конкретном источнике. Адаптировать для новых источников. Логика детекта провала:
```python
# Провал = title содержит "just a moment" или "attention required"
if "just a moment" in title.lower():
    await page.wait_for_timeout(10_000)  # дать Cloudflare ещё 10 сек
```
И проверка результата по индикаторам: наличие `<h1>`, контент-блок найден, НЕТ `cf-mitigated` в content.

#### `sitemap_loader.py` → взять паттерн обхода через Playwright
Для источников, у которых страница категории блокируется — загружать через тот же Playwright + stealth, не через httpx/requests. Функция `fetch_page()` универсальна.

#### `settings.py` → взять паттерн конфигурации
- Все настройки в `config.ini`, не в `.py` файлах
- `load_proxies()` — загрузка из `proxies.txt` с пропуском `#`-комментариев
- `setup_logging()` — двойной handler: файл + stdout

### Что НЕ брать
- SQLite (`database.py`) — у нас PostgreSQL
- Логику `urls_queue` / `slots` — у нас другая схема БД
- `iframe_extract.py` — специфично для того сайта

### Дополнительные зависимости Python
```
playwright==1.44.*
playwright-stealth==1.0.*
beautifulsoup4==4.12.*
fastapi==0.111.*
uvicorn[standard]==0.30.*
sqlalchemy[asyncio]==2.0.*
alembic==1.13.*
apscheduler==3.10.*
anthropic==0.28.*
python-telegram-bot==21.*
asyncpg==0.29.*
pydantic-settings==2.3.*
```

---

## 3. База данных

### 3.1 Полная схема

```sql
-- ============================================================
-- ИСТОЧНИКИ
-- ============================================================
CREATE TABLE sources (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(100) NOT NULL,        -- "legalbet.ro"
  base_url        TEXT NOT NULL,                -- "https://legalbet.ro"
  category_url    TEXT NOT NULL,                -- "/ponturi/" — страница со списком прогнозов
  language        VARCHAR(10) NOT NULL,         -- "ro", "en", "ru", "hu" и т.д.
  geo             VARCHAR(10),                  -- "RO", "GB", "RU" — целевое ГЕО
  is_active       BOOLEAN DEFAULT TRUE,
  scraper_module  VARCHAR(100),                 -- имя файла парсера: "legalbet"
  added_at        TIMESTAMP DEFAULT NOW(),
  last_checked_at TIMESTAMP,
  last_success_at TIMESTAMP,
  notes           TEXT                          -- произвольные заметки
);

-- ============================================================
-- МАТЧИ (одно событие для всех языков)
-- ============================================================
CREATE TABLE matches (
  id              SERIAL PRIMARY KEY,
  -- Уникальный ключ для дедупликации
  match_key       VARCHAR(300) UNIQUE NOT NULL, -- "{team_home_normalized}:{team_away_normalized}:{YYYY-MM-DD}"
  
  -- Канонические данные матча
  team_home       VARCHAR(150) NOT NULL,
  team_away       VARCHAR(150) NOT NULL,
  sport           VARCHAR(50),                  -- "football", "tennis", "handball"
  competition     VARCHAR(150),                 -- "Champions League", "Liga 1"
  match_date      TIMESTAMP,
  
  -- Slug для API
  slug            VARCHAR(300) UNIQUE,          -- "romania-vs-georgia-02-06-2025"
  
  -- AI-рекомендация (на английском)
  ai_summary      TEXT,
  ai_top_pick     VARCHAR(200),                 -- краткая главная ставка: "1 @ 1.85"
  ai_confidence   VARCHAR(20),                  -- "High" / "Medium" / "Low"
  ai_generated_at TIMESTAMP,
  ai_model        VARCHAR(100),                 -- версия модели Claude
  
  -- Мета
  predictions_count INTEGER DEFAULT 0,          -- денормализованный счётчик
  created_at      TIMESTAMP DEFAULT NOW(),
  updated_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ПРОГНОЗЫ (один прогноз = одна статья с одного источника)
-- ============================================================
CREATE TABLE predictions (
  id              SERIAL PRIMARY KEY,
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  source_id       INTEGER REFERENCES sources(id),
  
  source_url      TEXT NOT NULL UNIQUE,         -- оригинальный URL статьи
  title           TEXT,
  author          VARCHAR(150),
  language        VARCHAR(10) NOT NULL,         -- язык этого прогноза
  full_text       TEXT,                         -- полный текст анализа
  published_at    TIMESTAMP,
  scraped_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- СТАВКИ (одна prediction может содержать несколько ставок)
-- ============================================================
CREATE TABLE prediction_bets (
  id              SERIAL PRIMARY KEY,
  prediction_id   INTEGER REFERENCES predictions(id) ON DELETE CASCADE,
  bet_type        VARCHAR(100),                 -- "1X2", "Total Goals", "Both Teams Score"
  bet_pick        VARCHAR(100),                 -- "1", "Over 2.5", "Yes"
  odds            DECIMAL(8,2),
  is_main         BOOLEAN DEFAULT FALSE,        -- главная ставка в прогнозе
  sort_order      INTEGER DEFAULT 0
);

-- ============================================================
-- АЛЕРТЫ И HEALTH-CHECKS
-- ============================================================
CREATE TABLE scrape_logs (
  id              SERIAL PRIMARY KEY,
  source_id       INTEGER REFERENCES sources(id),
  status          VARCHAR(20) NOT NULL,         -- "success", "error", "partial"
  items_found     INTEGER DEFAULT 0,
  items_new       INTEGER DEFAULT 0,
  error_msg       TEXT,
  duration_ms     INTEGER,
  started_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE health_checks (
  id              SERIAL PRIMARY KEY,
  source_id       INTEGER REFERENCES sources(id),
  checked_at      TIMESTAMP DEFAULT NOW(),
  is_accessible   BOOLEAN,
  status_code     INTEGER,
  html_structure_ok BOOLEAN,                   -- парсер нашёл ожидаемые CSS-селекторы
  alert_sent      BOOLEAN DEFAULT FALSE,
  details         TEXT
);

-- ============================================================
-- ИНДЕКСЫ
-- ============================================================
CREATE INDEX idx_matches_match_key ON matches(match_key);
CREATE INDEX idx_matches_match_date ON matches(match_date);
CREATE INDEX idx_matches_sport ON matches(sport);
CREATE INDEX idx_predictions_match_id ON predictions(match_id);
CREATE INDEX idx_predictions_language ON predictions(language);
CREATE INDEX idx_prediction_bets_prediction_id ON prediction_bets(prediction_id);
CREATE INDEX idx_scrape_logs_source_id ON scrape_logs(source_id);
CREATE INDEX idx_health_checks_source_id ON health_checks(source_id);
```

---

## 4. Ключевая логика: дедупликация матчей

### 4.1 Формирование `match_key`

```python
# src/scraper/utils/match_key.py
import re
import unicodedata
from datetime import date

CLUB_PREFIXES = re.compile(r'\b(fc|fk|sc|ac|sk|bk|if|afc|cf|rc)\b', re.I)

def normalize_team_name(name: str) -> str:
    # убрать диакритику: ă→a, î→i, ș→s, ü→u и т.д.
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = CLUB_PREFIXES.sub("", name)   # убрать клубные суффиксы
    name = re.sub(r"[^a-z0-9]", "", name)  # только буквы и цифры
    return name.strip()

def build_match_key(team_home: str, team_away: str, match_date: date) -> str:
    home = normalize_team_name(team_home)
    away = normalize_team_name(team_away)
    return f"{home}:{away}:{match_date.isoformat()}"

# Примеры:
# "România" vs "Georgia" 2026-06-02  →  "romania:georgia:2026-06-02"
# "FC Barcelona" vs "Real Madrid"    →  "barcelona:realmadrid:2026-06-15"
```

### 4.2 Алгоритм поиска / создания матча

```python
# src/scraper/utils/match_key.py (продолжение)
from datetime import timedelta
from sqlalchemy import select
from ...db.models import Match
from ...db.session import AsyncSession

async def find_or_create_match(session: AsyncSession, data: dict) -> Match:
    key = build_match_key(data["team_home"], data["team_away"], data["match_date"].date())

    # 1. Точное совпадение
    match = await session.scalar(select(Match).where(Match.match_key == key))
    if match:
        return match

    # 2. Мягкий поиск ±1 день (разные источники могут давать разное время)
    day = data["match_date"].date()
    match = await session.scalar(
        select(Match).where(
            Match.match_key.like(f"{normalize_team_name(data['team_home'])}:{normalize_team_name(data['team_away'])}:%"),
            Match.match_date >= day - timedelta(days=1),
            Match.match_date <= day + timedelta(days=1),
        )
    )
    if match:
        return match

    # 3. Создаём новый
    match = Match(
        match_key=key,
        team_home=data["team_home"],
        team_away=data["team_away"],
        sport=data.get("sport"),
        competition=data.get("competition"),
        match_date=data["match_date"],
        slug=build_slug(data["team_home"], data["team_away"], data["match_date"].date()),
    )
    session.add(match)
    await session.flush()
    return match
```

---

## 5. Архитектура парсера

### 5.1 Структура файлов

```
src/
├── scraper/
│   ├── engine.ts               — общий движок: обход страниц, retry, логирование
│   ├── scheduler.ts            — cron-задачи
│   ├── healthCheck.ts          — проверка доступности источников
│   │
│   ├── sources/                — по одному файлу на источник
│   │   ├── _template.ts        — ШАБЛОН для новых источников
│   │   ├── beturi.ts
│   │   └── pontulzilei.ts
│   │
│   └── utils/
│       ├── browser.ts          — singleton Playwright
│       ├── matchKey.ts         — нормализация и ключи матчей
│       ├── normalizer.ts       — даты, коэффициенты, виды спорта
│       └── alerter.ts          — отправка уведомлений в Telegram
│
├── api/
│   ├── server.ts               — Fastify app
│   └── routes/
│       ├── matches.ts
│       ├── predictions.ts
│       ├── sources.ts
│       └── admin.ts
│
├── ai/
│   └── summarizer.ts           — генерация AI-рекомендаций через Claude
│
├── bot/
│   └── telegram.ts             — Telegram бот
│
└── db/
    └── prisma/
        └── schema.prisma
```

### 5.2 Шаблон источника

Полный шаблон с примерами — см. **раздел 12** («Шаблон источника `sources/_template.py`»).

Ключевые принципы каждого источника:
- `get_article_urls(page)` — страница категории → список URL
- `parse_prediction(page, url)` → словарь с полями матча, автора, текста и списком `bets[]`
- Cloudflare-детект (`"just a moment"` в title) — пауза 10 сек (паттерн из `reference_scraper/diagnose.py`)
- Всегда использовать `browser.py` фабрику, не создавать browser/context вручную

### 5.3 Алгоритм обработки источника

```
ДЛЯ КАЖДОГО активного источника:
  1. getArticleUrls() → список URL
  2. Фильтровать: оставить только URL не старше 7 дней (по URL или заголовку)
  3. Проверить в БД: исключить уже обработанные source_url
  4. ДЛЯ КАЖДОГО нового URL:
     a. parsePrediction() → ParsedPrediction
     b. findOrCreateMatch() → match
     c. Сохранить prediction в БД
     d. Сохранить prediction_bets[] в БД
     e. Инкрементировать matches.predictions_count
     f. Пауза 2–5 сек (random)
  5. Записать в scrape_logs (success / error / partial)
  6. Обновить sources.last_success_at
```

### 5.4 Расписание (cron)

| Задача | Расписание | Описание |
|--------|-----------|----------|
| Полный парсинг всех источников | `0 */4 * * *` | Каждые 4 часа |
| Быстрая проверка новых URL | `*/30 * * * *` | Каждые 30 минут |
| Генерация AI-рекомендаций | `15 */2 * * *` | Каждые 2 часа |
| Health-check всех источников | `0 8 * * *` | Ежедневно в 08:00 |

---

## 6. Health-Check и алерты

### 6.1 Что проверяется ежедневно

```python
# src/scraper/health_check.py
async def check_source(source: Source) -> HealthCheckResult:
    # 1. HTTP статус (200 OK?)
    # 2. Доступность страницы категории через Playwright + stealth
    # 3. Наличие ожидаемых CSS-селекторов (проверка верстки)
    # 4. Количество статей найдено > 0 ?
    # 5. Последний успешный парсинг был не более 12 часов назад?
    # Паттерн запуска браузера — из reference_scraper/diagnose.py
    ...
```

### 6.2 Триггеры алертов в Telegram

| Событие | Сообщение |
|---------|-----------|
| Парсинг источника завершился с ошибкой | `⚠️ [legalbet.ro] Scrape failed: {error_msg}` |
| Источник недоступен (HTTP != 200) | `🔴 [pariurix.com] Site unreachable (503)` |
| CSS-селекторы не найдены (изменилась верстка) | `🔧 [beturi.ro] Layout changed — selectors not found` |
| Нет новых прогнозов >24ч у активного источника | `📭 [pontul-zilei.com] No new predictions in 24h` |
| AI-генерация провалилась | `🤖 AI summary failed for match_id={id}: {error}` |

---

## 7. AI-рекомендации

### 7.1 Когда запускать

```typescript
// Условия для генерации/обновления ai_summary:
const needsAI = 
  match.predictions_count >= 2 &&
  (match.ai_generated_at === null || 
   match.updated_at > match.ai_generated_at);
```

### 7.2 Промпт для Claude (ответ на английском)

```typescript
const prompt = `
You are a professional sports betting analyst. Below are predictions from multiple expert tipsters for the same match.

Match: ${match.teamHome} vs ${match.teamAway}
Date: ${match.matchDate}
Competition: ${match.competition}
Sport: ${match.sport}

Expert Predictions:
${predictions.map(p => `
Source: ${p.source.name} (${p.language})
Bets: ${p.bets.map(b => `${b.betPick} @ ${b.odds}`).join(', ')}
Analysis: ${p.fullText?.slice(0, 500)}
---`).join('\n')}

Task: Write a concise consensus summary in ENGLISH (4–6 sentences):
1. What do most experts agree on?
2. The main recommended bet and odds range
3. Confidence level: High / Medium / Low
4. Any important risk factors mentioned

Important: Respond ONLY in English. Be concise and analytical, not promotional.
Return JSON:
{
  "summary": "...",
  "top_pick": "Over 2.5 @ ~1.80",
  "confidence": "Medium"
}
`;
```

### 7.3 Сохранение результата

```typescript
// Парсим JSON из ответа Claude, сохраняем в matches:
await db.matches.update({
  where: { id: match.id },
  data: {
    ai_summary: result.summary,
    ai_top_pick: result.top_pick,
    ai_confidence: result.confidence,
    ai_generated_at: new Date(),
    ai_model: 'claude-sonnet-4-20250514'
  }
});
```

---

## 8. REST API

Все эндпоинты отдают JSON. Аутентификация: `Bearer token` в заголовке для admin-маршрутов.

### 8.1 Публичные эндпоинты (для SEO-сайтов)

```
GET /api/v1/matches
  Параметры: sport, date_from, date_to, language, page, limit
  Ответ: список матчей с ai_summary, predictions_count, top_pick

GET /api/v1/matches/:slug
  Ответ: матч + все прогнозы + ставки (сгруппированы по языку и источнику)
  
GET /api/v1/matches/:slug/predictions
  Параметры: language (фильтр по языку прогнозов)
  Ответ: только прогнозы для этого матча

GET /api/v1/sports
  Ответ: список видов спорта с количеством матчей
```

### 8.2 Пример ответа `GET /api/v1/matches/:slug`

```json
{
  "match": {
    "id": 42,
    "slug": "romania-vs-georgia-02-06-2026",
    "teamHome": "Romania",
    "teamAway": "Georgia",
    "sport": "football",
    "competition": "International Friendly",
    "matchDate": "2026-06-02T20:00:00Z",
    "predictionsCount": 5,
    "ai": {
      "summary": "Most tipsters agree Romania will control the game...",
      "topPick": "Romania Win @ 1.75",
      "confidence": "Medium",
      "generatedAt": "2026-06-02T10:15:00Z"
    }
  },
  "predictions": [
    {
      "id": 101,
      "source": "beturi.ro",
      "language": "ro",
      "author": "Cristi Geiger",
      "title": "Romania vs Georgia: Ponturi...",
      "sourceUrl": "https://beturi.ro/ponturi-pariuri/...",
      "publishedAt": "2026-06-02T08:00:00Z",
      "bets": [
        { "betType": "1X2", "betPick": "1", "odds": 1.75, "isMain": true },
        { "betType": "Total Goals", "betPick": "Over 2.5", "odds": 1.90, "isMain": false }
      ]
    }
  ]
}
```

### 8.3 Admin эндпоинты (защищены ADMIN_API_KEY)

```
GET  /api/v1/admin/sources              — список всех источников
POST /api/v1/admin/sources              — добавить источник
PUT  /api/v1/admin/sources/:id          — обновить источник
DEL  /api/v1/admin/sources/:id          — деактивировать источник

POST /api/v1/admin/scrape/run           — запустить парсинг (all или source_id)
POST /api/v1/admin/matches/:id/regenerate-ai — перегенерировать AI-рекомендацию

GET  /api/v1/admin/logs                 — последние scrape_logs
GET  /api/v1/admin/health               — последние health_checks
```

---

## 9. Telegram Бот

### 9.1 Команды

| Команда | Описание |
|---------|----------|
| `/status` | Статус всех активных источников (последний парсинг, количество прогнозов) |
| `/sources` | Список всех источников с флагами активности |
| `/add_source` | Интерактивный диалог добавления нового источника |
| `/scrape [source_name]` | Запустить парсинг немедленно (всех или конкретного) |
| `/diagnose [source_name]` | Запустить диагностику Cloudflare для источника |
| `/health` | Результаты последнего health-check |
| `/logs [N]` | Последние N записей из scrape_logs (default 10) |
| `/match [slug]` | Информация о матче и статус AI |

### 9.2 Диалог `/add_source`

```
Бот: Введите base URL источника (например: https://example.com)
→ Пользователь: https://newsource.com

Бот: Введите URL страницы категории с прогнозами
→ Пользователь: /ponturi-sportive/

Бот: Язык контента (ro/en/ru/hu/...)?
→ Пользователь: en

Бот: ГЕО (RO/GB/RU/...)?
→ Пользователь: GB

Бот: Источник добавлен в БД (is_active=false).
Cursor должен создать файл src/scraper/sources/newsource.py по шаблону _template.py,
запустить диагностику командой /diagnose newsource и проверить парсинг /scrape newsource.
```

### 9.3 Формат алертов

```
🔴 SCRAPE ERROR
Source: legalbet.ro
Time: 2026-06-02 14:32 UTC
Error: Timeout waiting for selector ".prediction-card"
Last success: 8h ago

[Retry now] [Disable source]
```
> Кнопки — inline keyboard с callback_data для быстрых действий.

---

## 10. Переменные окружения

```env
# БД
DATABASE_URL=postgresql://user:pass@localhost:5432/predictions_db

# AI
ANTHROPIC_API_KEY=sk-ant-...

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...        # ваш chat_id для алертов

# API
ADMIN_API_KEY=...                 # Bearer-токен для /admin маршрутов
PORT=8000

# Парсер
SCRAPE_MAX_RETRIES=3
SCRAPE_DELAY_MIN=2.0
SCRAPE_DELAY_MAX=5.0
SCRAPE_ARTICLES_MAX_AGE_DAYS=7
REQUIRE_PROXY=true
HEADLESS=true
```

Дублировать в `config.ini` (паттерн из `reference_scraper/settings.py`) — это основной файл конфигурации, `.env` только для секретов.

---

## 11. Структура проекта

```
/
├── reference_scraper/          ← ТОЛЬКО ДЛЯ ЧТЕНИЯ, не изменять
│   ├── proxy_pool.py
│   ├── scraper.py
│   ├── diagnose.py
│   ├── sitemap_loader.py
│   └── settings.py
│
├── src/
│   ├── scraper/
│   │   ├── engine.py
│   │   ├── scheduler.py
│   │   ├── health_check.py
│   │   ├── diagnose.py         — адаптирован из reference
│   │   ├── proxy_pool.py       — взят из reference
│   │   ├── sources/
│   │   │   ├── _template.py    ← шаблон для новых источников
│   │   │   ├── beturi.py
│   │   │   └── pontulzilei.py
│   │   └── utils/
│   │       ├── browser.py
│   │       ├── match_key.py
│   │       ├── normalizer.py
│   │       └── alerter.py
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │       ├── matches.py
│   │       ├── predictions.py
│   │       └── admin.py
│   ├── ai/
│   │   └── summarizer.py
│   ├── bot/
│   │   └── telegram.py
│   └── db/
│       ├── models.py
│       └── session.py
├── alembic/
│   └── versions/
├── config.ini
├── proxies.txt
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 12. Шаблон источника (`sources/_template.py`)

```python
"""
Шаблон парсера источника. Cursor копирует этот файл и заполняет селекторы.
Добавление нового источника = заполнить этот файл + добавить запись в таблицу sources.
"""
from __future__ import annotations
from playwright.async_api import Page
from ..utils.browser import new_page   # фабрика с stealth + proxy (из reference)
from ..utils.normalizer import parse_date, parse_odds

SOURCE_CONFIG = {
    "name": "SITE_NAME",          # заполнить
    "base_url": "https://...",    # заполнить
    "category_url": "/ponturi/",  # заполнить
    "language": "ro",             # заполнить: ro / en / ru / hu / ...
    "geo": "RO",                  # заполнить: RO / GB / RU / ...
}

async def get_article_urls(page: Page) -> list[str]:
    """Со страницы категории собрать URL отдельных прогнозов."""
    await page.goto(SOURCE_CONFIG["base_url"] + SOURCE_CONFIG["category_url"])
    await page.wait_for_timeout(3000)  # ждать Cloudflare (паттерн из reference/scraper.py)
    # TODO: заполнить CSS-селектор
    return await page.eval_on_selector_all("SELECTOR a", "els => els.map(e => e.href)")

async def parse_prediction(page: Page, url: str) -> dict | None:
    """С отдельной страницы прогноза извлечь данные."""
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # Детект Cloudflare (паттерн из reference/diagnose.py)
    title = await page.title()
    if "just a moment" in title.lower():
        await page.wait_for_timeout(10_000)

    return {
        "source_url": url,
        "title":       await page.eval_on_selector("SELECTOR", "el => el.textContent.trim()"),
        "team_home":   "",     # TODO
        "team_away":   "",     # TODO
        "sport":       "",     # TODO: нормализовать через normalizer.py
        "competition": "",     # TODO
        "match_date":  None,   # TODO: parse_date(raw_string)
        "author":      "",     # TODO (опционально)
        "full_text":   "",     # TODO: полный текст анализа
        "published_at": None,  # TODO
        "bets": [
            # TODO: массив ставок — сайт может содержать несколько
            {"bet_type": "", "bet_pick": "", "odds": 0.0, "is_main": True}
        ]
    }
```

---

## 13. MVP — порядок разработки

**Итерация 1 — Ядро:**
1. ✅ Изучить `reference_scraper/` (обязательно перед кодингом)
2. ✅ SQLAlchemy-модели + Alembic-миграции, Docker Compose с PostgreSQL
3. ✅ `proxy_pool.py` — скопировать из reference, адаптировать импорты
4. ✅ `browser.py` — фабрика с stealth + proxy (паттерны из reference)
5. ✅ `match_key.py` — нормализация и дедупликация матчей

**Итерация 2 — Первые парсеры:**
6. ✅ `_template.py` + `beturi.py` + `pontulzilei.py`
7. ✅ `engine.py` — запуск, retry (`_PROXY_ERRORS` паттерн из reference), логирование
8. ✅ `scheduler.py` — APScheduler расписание

**Итерация 3 — AI и API:**
9. ✅ `summarizer.py` — Claude API, JSON-ответ
10. ✅ REST API: `GET /matches`, `GET /matches/:slug`

**Итерация 4 — Мониторинг:**
11. ✅ `health_check.py` + `diagnose.py`
12. ✅ Telegram бот — алерты + `/status`, `/health`, `/logs`
13. ✅ Telegram бот — `/add_source` диалог

**Отложить:**
- Остальные источники (добавляются по одному через бота)
- Admin REST API (управление через бота покрывает MVP)

---

## 14. README.md должен содержать

- `docker-compose up` — поднять всё локально
- `alembic upgrade head` — применить схему
- Как добавить новый источник (скопировать `_template.py`, заполнить, добавить запись в sources)
- Как запустить разовый парсинг: `python -m src.scraper.engine --source beturi`
- Как запустить диагностику: `python -m src.scraper.diagnose --source beturi`
- Описание `proxies.txt` и `config.ini`

---

## Примечания для Cursor

- **Первый шаг — прочитать `reference_scraper/`**, особенно `proxy_pool.py`, `scraper.py`, `diagnose.py`
- `proxy_pool.py` переносится почти без изменений — менять только импорты
- Все browser-контексты создаются через единую фабрику `browser.py`, чтобы stealth и прокси применялись везде одинаково
- `match_key` — единственный источник истины для дедупликации матчей на всех языках
- Все ошибки парсера — `try/except` с записью в `scrape_logs` и отправкой в Telegram
- Источник добавляется через бота → Cursor создаёт `.py` по шаблону → `diagnose` → активация
- AI-промпт всегда требует JSON, парсить через `json.loads()`, обёрнуть в `try/except`
- Источников будет 50+, `engine.py` должен быть полностью универсальным

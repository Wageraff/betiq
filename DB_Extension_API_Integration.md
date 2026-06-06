# BetIQ — Расширение БД под API-Football v3 + The Odds API v4

> **Миграция:** добавляется к существующей схеме (migration `011` и далее).  
> **Принцип:** существующие таблицы не ломаются, новые — добавляются.

---

## Обзор: что добавляем и зачем

```
Существующее ядро:          Новые слои:
teams                  →    + teams.logo_url (автозагрузка из API)
matches                →    + matches.status, venue, season, round
                            + match_external_ids  (fixture_id ↔ odds_event_id)
                            + competitions        (справочник лиг с logo)
                            + competition_ext_ids (league_id у провайдеров)
                       →    [FOOTBALL ONLY]
                            + match_stats         (нормализованная статистика)
                            + match_lineups        (составы)
                            + team_form           (форма: последние N матчей)
                       →    [ALL SPORTS — через The Odds API]
                            + match_odds          (коэффициенты по букмекерам)
                            + odds_history        (движение линий)
                       →    [ASSETS]
                            + media_assets        (картинки команд/лиг с CDN)
```

---

## Миграция 011 — Расширение таблицы `teams`

Добавить два поля в существующую таблицу `teams`:

```sql
ALTER TABLE teams
  ADD COLUMN IF NOT EXISTS logo_url       VARCHAR(500),   -- URL с CDN api-sports.io
  ADD COLUMN IF NOT EXISTS logo_fetched_at TIMESTAMPTZ;   -- когда последний раз обновляли
```

**Откуда берётся `logo_url`:**

API-Football возвращает в каждом ответе, где есть команда:
```json
"team": {
  "id": 463,
  "name": "Aldosivi",
  "logo": "https://media.api-sports.io/football/teams/463.png"
}
```

URL стабильный, хостится на CDN api-sports.io — можно хранить напрямую и отдавать клиентам без скачивания на свой сервер. Для других видов спорта (hockey, basketball и т.д.) формат аналогичный, путь меняется: `media.api-sports.io/hockey/teams/ID.png`.

**Логика заполнения:**

```python
# src/api_clients/api_football.py
async def sync_team_logo(team: Team, api_team_data: dict):
    logo_url = api_team_data.get("logo")
    if logo_url and not team.logo_url:  # не перезаписывать ручную загрузку
        await db.execute(
            "UPDATE teams SET logo_url = $1, logo_fetched_at = NOW() WHERE id = $2",
            logo_url, team.id
        )
```

Логика приоритета: `logo_path` (ручная загрузка в админке) > `logo_url` (из API). При отображении — если `logo_path` заполнен, используем его; иначе `logo_url`.

---

## Миграция 012 — Справочник соревнований `competitions`

Сейчас `matches.competition` — просто строка. Нужна отдельная таблица чтобы хранить logo и external IDs лиг.

```sql
CREATE TABLE competitions (
  id              SERIAL PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  sport           VARCHAR(50)  NOT NULL,
  country         VARCHAR(100),
  country_code    VARCHAR(5),              -- "GB", "DE", "INT"
  logo_url        VARCHAR(500),            -- из API-Football: media.api-sports.io/football/leagues/39.png
  flag_url        VARCHAR(500),            -- флаг страны
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_competitions_name_sport
  ON competitions (lower(name), sport);

-- Внешние ID лиги у провайдеров
CREATE TABLE competition_external_ids (
  competition_id  INTEGER REFERENCES competitions(id) ON DELETE CASCADE,
  provider        VARCHAR(30) NOT NULL,    -- 'api_football', 'the_odds_api', 'sportradar'
  external_id     VARCHAR(100) NOT NULL,   -- у api-football: "39" (Premier League)
  external_name   VARCHAR(200),            -- как называется у провайдера
  season          VARCHAR(10),             -- "2025" или "2024/2025"
  PRIMARY KEY (competition_id, provider)
);

-- Добавить FK в matches (nullable — старые записи не сломаются)
ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS competition_id INTEGER REFERENCES competitions(id) ON DELETE SET NULL;

CREATE INDEX idx_matches_competition_id ON matches(competition_id);
```

**Пример данных из API-Football `/leagues`:**
```json
{
  "league": { "id": 39, "name": "Premier League", "type": "League",
              "logo": "https://media.api-sports.io/football/leagues/39.png" },
  "country": { "name": "England", "code": "GB",
               "flag": "https://media.api-sports.io/flags/gb.svg" },
  "seasons": [{ "year": 2025, "current": true }]
}
```

**The Odds API** использует строковые sport_key вида `soccer_england_premier_league` — они хранятся в `competition_external_ids` с `provider = 'the_odds_api'`.

---

## Миграция 013 — Маппинг внешних ID матча

Центральная таблица связи: наш `matches.id` ↔ `fixture_id` у api-football ↔ `event_id` у the-odds-api.

```sql
CREATE TABLE match_external_ids (
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  provider        VARCHAR(30) NOT NULL,
  -- 'api_football' → fixture_id (integer как строка: "215662")
  -- 'the_odds_api' → event_id (UUID: "bda33adca828c09dc3cac3a856aef176")
  external_id     VARCHAR(100) NOT NULL,
  linked_at       TIMESTAMPTZ DEFAULT NOW(),
  link_method     VARCHAR(20) DEFAULT 'auto',  -- 'auto' | 'manual'
  confidence      FLOAT,                       -- 0.0–1.0 при авто-матчинге
  PRIMARY KEY (match_id, provider)
);

CREATE INDEX idx_match_ext_provider_id ON match_external_ids(provider, external_id);
```

**Алгоритм линковки (auto):**

```python
# src/api_clients/linker.py

async def link_match_to_api_football(match: Match) -> bool:
    """
    Ищем fixture в API-Football по:
    1. team_external_ids обеих команд (если уже есть) + match_date ±3h
    2. Fuzzy match по именам команд + match_date ±3h
    """
    # Шаг 1: получаем внешние ID команд
    home_ext = await get_team_external_id(match.team_home_id, 'api_football')
    away_ext = await get_team_external_id(match.team_away_id, 'api_football')

    if home_ext and away_ext:
        # Точный запрос: /fixtures?team=HOME_ID&season=2025&date=YYYY-MM-DD
        fixtures = await api_football.get_fixtures(
            team=home_ext,
            date=match.match_date.date().isoformat()
        )
        for f in fixtures:
            if f['teams']['away']['id'] == int(away_ext):
                await save_external_id(match.id, 'api_football', str(f['fixture']['id']),
                                       method='auto', confidence=1.0)
                return True

    # Шаг 2: fuzzy через /fixtures?date=DATE
    # ...
    return False


async def link_match_to_odds_api(match: Match) -> bool:
    """
    The Odds API не имеет endpoint поиска по командам.
    Загружаем все события спорта на дату и матчим по именам.
    """
    sport_key = SPORT_TO_ODDS_KEY.get(match.sport)  # 'football' → 'soccer_...'
    if not sport_key:
        return False

    events = await the_odds_api.get_events(sport_key)
    for event in events:
        if (fuzzy_match(event['home_team'], match.team_home) and
            fuzzy_match(event['away_team'], match.team_away) and
            abs((parse_dt(event['commence_time']) - match.match_date).total_seconds()) < 10800):
            await save_external_id(match.id, 'the_odds_api', event['id'],
                                   method='auto', confidence=0.9)
            return True
    return False
```

---

## Миграция 014 — Внешние ID команд

```sql
CREATE TABLE team_external_ids (
  team_id         INTEGER REFERENCES teams(id) ON DELETE CASCADE,
  provider        VARCHAR(30) NOT NULL,
  external_id     VARCHAR(100) NOT NULL,
  external_name   VARCHAR(200),           -- имя команды как в API
  verified        BOOLEAN DEFAULT FALSE,  -- подтверждено вручную
  PRIMARY KEY (team_id, provider)
);
```

**Заполнение:** при первом успешном `link_match_to_api_football()` — сохраняем `team_id` обеих команд. После ручной верификации в боте — `verified = true`. Верифицированные ID используются для точных запросов, неверифицированные — только для авто-матчинга.

---

## Миграция 015 — Расширение таблицы `matches`

Поля которых сейчас нет, но нужны после подключения API:

```sql
ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS status         VARCHAR(20),
  -- 'NS' (not started) | '1H' | 'HT' | '2H' | 'ET' | 'FT' | 'PST' | 'CANC'
  -- The Odds API: 'upcoming' | 'live' | 'completed'

  ADD COLUMN IF NOT EXISTS venue_name     VARCHAR(200),
  ADD COLUMN IF NOT EXISTS venue_city     VARCHAR(100),

  ADD COLUMN IF NOT EXISTS season         VARCHAR(10),    -- "2025" или "2024/2025"
  ADD COLUMN IF NOT EXISTS round          VARCHAR(50),    -- "Regular Season - 12"

  ADD COLUMN IF NOT EXISTS score_home     SMALLINT,
  ADD COLUMN IF NOT EXISTS score_away     SMALLINT,
  ADD COLUMN IF NOT EXISTS score_ht_home  SMALLINT,       -- счёт первого тайма
  ADD COLUMN IF NOT EXISTS score_ht_away  SMALLINT,

  ADD COLUMN IF NOT EXISTS stats_fetched_at   TIMESTAMPTZ,  -- когда последний раз тянули статистику
  ADD COLUMN IF NOT EXISTS odds_fetched_at    TIMESTAMPTZ;

CREATE INDEX idx_matches_status ON matches(status);
```

---

## Миграция 016 — Статистика матча `match_stats` (только football)

Нормализованные данные из `/fixtures/statistics`. Две строки на матч (home + away).

```sql
CREATE TABLE match_stats (
  id                  SERIAL PRIMARY KEY,
  match_id            INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  team_id             INTEGER REFERENCES teams(id) ON DELETE SET NULL,
  side                VARCHAR(5) NOT NULL,          -- 'home' | 'away'
  half                VARCHAR(5) DEFAULT 'full',    -- 'full' | '1h' | '2h'

  -- Удары
  shots_on_goal       SMALLINT,
  shots_off_goal      SMALLINT,
  shots_total         SMALLINT,
  shots_blocked       SMALLINT,
  shots_insidebox     SMALLINT,
  shots_outsidebox    SMALLINT,

  -- Ключевые показатели для ставочников
  corners             SMALLINT,
  fouls               SMALLINT,
  yellow_cards        SMALLINT,
  red_cards           SMALLINT,
  offsides            SMALLINT,
  possession          SMALLINT,                     -- %

  -- Дополнительно
  passes_total        SMALLINT,
  passes_accurate     SMALLINT,
  goalkeeper_saves    SMALLINT,

  fetched_at          TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (match_id, side, half)
);

CREATE INDEX idx_match_stats_match_id ON match_stats(match_id);
CREATE INDEX idx_match_stats_team_id  ON match_stats(team_id);
```

**Откуда:** `GET /fixtures/statistics?fixture=FIXTURE_ID`

Запрос делается **1 раз** — после окончания матча (статус `FT`). Данные не меняются.

---

## Миграция 017 — Форма команды `team_form` (только football)

История последних матчей команды — для AI-промпта и отображения на сайте.

```sql
CREATE TABLE team_form (
  id                  SERIAL PRIMARY KEY,
  team_id             INTEGER REFERENCES teams(id) ON DELETE CASCADE,
  fixture_external_id VARCHAR(50),                  -- fixture_id из API-Football
  match_date          DATE NOT NULL,
  opponent_name       VARCHAR(150),
  opponent_id         INTEGER REFERENCES teams(id) ON DELETE SET NULL,
  is_home             BOOLEAN,

  result              CHAR(1),                      -- 'W' | 'D' | 'L'
  goals_scored        SMALLINT,
  goals_conceded      SMALLINT,
  corners_for         SMALLINT,
  corners_against     SMALLINT,
  yellow_cards        SMALLINT,

  competition_name    VARCHAR(150),

  UNIQUE (team_id, fixture_external_id)
);

CREATE INDEX idx_team_form_team_date ON team_form(team_id, match_date DESC);
```

**Откуда:** `GET /fixtures?team=TEAM_ID&last=10`  
Запрос делается при создании нового матча + ежедневное обновление по расписанию.

---

## Миграция 018 — Составы `match_lineups` (только football)

```sql
CREATE TABLE match_lineups (
  id              SERIAL PRIMARY KEY,
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  team_id         INTEGER REFERENCES teams(id) ON DELETE SET NULL,
  side            VARCHAR(5),                 -- 'home' | 'away'
  formation       VARCHAR(20),                -- "4-3-3"
  coach_name      VARCHAR(150),
  coach_photo_url VARCHAR(500),
  lineup_json     JSONB,                      -- полный состав: [{player_id, name, number, pos, photo_url}]
  fetched_at      TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (match_id, side)
);
```

**Откуда:** `GET /fixtures/lineups?fixture=FIXTURE_ID`  
Появляются за ~1ч до матча. Запрашивать при статусе матча `NS` в течение последних 2 часов до кикофа.

`photo_url` игрока — `https://media.api-sports.io/football/players/PLAYER_ID.png` — хранится внутри `lineup_json`.

---

## Миграция 019 — Коэффициенты `match_odds` (все виды спорта)

Основная таблица для данных из **The Odds API**. Для football — дополнительно из API-Football (`/odds`).

```sql
CREATE TABLE match_odds (
  id              SERIAL PRIMARY KEY,
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  sport           VARCHAR(50) NOT NULL,       -- денормализовано для быстрой выборки
  bookmaker       VARCHAR(80) NOT NULL,       -- 'bet365', 'pinnacle', 'unibet', ...
  market          VARCHAR(80) NOT NULL,
  -- The Odds API markets: 'h2h', 'spreads', 'totals', 'outrights'
  -- API-Football markets: 'Match Winner', 'Goals Over/Under', 'Both Teams Score', 'Asian Handicap'
  outcome         VARCHAR(100) NOT NULL,      -- 'Home', 'Away', 'Draw', 'Over 2.5', 'Yes'
  odds            NUMERIC(8,2) NOT NULL,
  point           NUMERIC(6,2),              -- для totals/spreads: 2.5, -1.5, ...
  is_live         BOOLEAN DEFAULT FALSE,
  recorded_at     TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (match_id, bookmaker, market, outcome, is_live)
  -- при обновлении — ON CONFLICT DO UPDATE SET odds=..., recorded_at=...
);

CREATE INDEX idx_match_odds_match_id   ON match_odds(match_id);
CREATE INDEX idx_match_odds_sport      ON match_odds(sport);
CREATE INDEX idx_match_odds_bookmaker  ON match_odds(bookmaker);
CREATE INDEX idx_match_odds_market     ON match_odds(market);
```

---

## Миграция 020 — История коэффициентов `odds_history`

Для отслеживания движения линий (dropping odds). Снимок каждый раз при изменении > 0.05.

```sql
CREATE TABLE odds_history (
  id              SERIAL PRIMARY KEY,
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  bookmaker       VARCHAR(80) NOT NULL,
  market          VARCHAR(80) NOT NULL,
  outcome         VARCHAR(100) NOT NULL,
  odds_prev       NUMERIC(8,2),
  odds_curr       NUMERIC(8,2) NOT NULL,
  movement_pct    NUMERIC(5,2),              -- (odds_curr - odds_prev) / odds_prev * 100
  direction       CHAR(4),                   -- 'UP' | 'DOWN'
  is_significant  BOOLEAN DEFAULT FALSE,     -- движение > 10% — алерт
  recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_odds_history_match_id     ON odds_history(match_id);
CREATE INDEX idx_odds_history_significant  ON odds_history(is_significant, recorded_at DESC);
```

**Логика записи:**
```python
async def update_odds(match_id, bookmaker, market, outcome, new_odds):
    prev = await db.get_current_odds(match_id, bookmaker, market, outcome)
    if prev is None:
        await db.insert_odds(...)
        return

    movement = (new_odds - prev.odds) / prev.odds * 100
    if abs(movement) >= 5:  # записываем только значимые изменения
        await db.insert_odds_history(
            match_id=match_id,
            odds_prev=prev.odds,
            odds_curr=new_odds,
            movement_pct=movement,
            direction='DOWN' if movement < 0 else 'UP',
            is_significant=abs(movement) >= 10
        )
    await db.upsert_current_odds(match_id, bookmaker, market, outcome, new_odds)
```

---

## Миграция 021 — Кэш AI-ответов чат-бота

```sql
CREATE TABLE ai_chat_cache (
  id              SERIAL PRIMARY KEY,
  cache_key       VARCHAR(300) UNIQUE NOT NULL,
  -- формат: "{match_id}:{question_type}:{lang}"
  -- пример: "4521:corners:ro"
  match_id        INTEGER REFERENCES matches(id) ON DELETE CASCADE,
  question_type   VARCHAR(50) NOT NULL,
  -- 'outcome' | 'corners' | 'btts' | 'value_bet' | 'h2h' | 'form' | 'lineups' | 'general'
  language        VARCHAR(10) NOT NULL,
  response_text   TEXT NOT NULL,
  tokens_input    INTEGER,
  tokens_output   INTEGER,
  generated_at    TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NOT NULL,       -- обычно = match_date + 2h
  hit_count       INTEGER DEFAULT 0           -- сколько раз отдали из кэша
);

CREATE INDEX idx_ai_cache_key        ON ai_chat_cache(cache_key);
CREATE INDEX idx_ai_cache_expires    ON ai_chat_cache(expires_at);
CREATE INDEX idx_ai_cache_match      ON ai_chat_cache(match_id);
```

---

## Итоговая диаграмма (новые связи)

```
competitions ──────────────────────── competition_external_ids
     │
     │ competition_id (nullable FK)
     ↓
   matches ──── match_external_ids ── (api_football fixture_id)
     │                             └── (the_odds_api event_id)
     │
     ├──► match_stats        (football: shots, corners, cards — post-match)
     ├──► match_lineups      (football: formations, players — pre-match)
     ├──► match_odds         (ALL sports: bookmaker lines — live update)
     ├──► odds_history       (ALL sports: line movement snapshots)
     └──► ai_chat_cache      (pre-generated Claude responses)

   teams ────── team_external_ids ─── (api_football team_id)
     │
     ├──► logo_url           (CDN url из API, новое поле)
     └──► team_form          (football: last 10 results per team)
```

---

## Расписание fetch-задач (APScheduler)

| Задача | Расписание | Источник | Что делаем |
|--------|-----------|----------|------------|
| Sync leagues | `0 6 * * *` | API-Football | Обновить `competitions` + `competition_external_ids` |
| Sync team logos | `0 7 * * 1` | API-Football | Заполнить `teams.logo_url` где пусто |
| Link new matches | `*/15 * * * *` | API-Football + The Odds API | `match_external_ids` для матчей без линковки |
| Fetch pre-match stats | `0 */6 * * *` | API-Football | `team_form` для матчей ближайших 48h |
| Fetch lineups | `0,30 * * * *` | API-Football | `match_lineups` для матчей через < 2h |
| Fetch odds (football) | `*/10 * * * *` | The Odds API | `match_odds` + `odds_history` для активных матчей |
| Fetch odds (other sports) | `*/20 * * * *` | The Odds API | `match_odds` теннис/крикет/хоккей |
| Fetch post-match stats | `*/5 * * * *` | API-Football | `match_stats` для матчей со статусом FT (сразу после окончания) |
| Pregenerate AI cache | `0 7 * * *` | Claude API | `ai_chat_cache` для матчей дня |
| Cleanup expired cache | `0 4 * * *` | — | DELETE FROM ai_chat_cache WHERE expires_at < NOW() |

---

## Контроль запросов API (экономия лимитов)

### API-Football (7500 запросов/день на Pro)

Стратегия: **не тянуть то, что уже есть**.

```python
# Перед каждым fetch-запросом проверять:

# 1. Статистика — только для завершённых матчей, только если не тянули
if match.status == 'FT' and match.stats_fetched_at is None:
    await fetch_and_save_stats(fixture_id)

# 2. Коэффициенты API-Football — только football, только pre-match
# The Odds API дешевле для этой задачи, API-Football используем как резерв

# 3. Форма команд — обновлять не чаще раза в день
if not team.form_updated_today:
    await fetch_team_form(team_ext_id)

# 4. Составы — только когда матч через < 2h
if time_to_match < timedelta(hours=2):
    await fetch_lineups(fixture_id)
```

Примерный дневной расход (50 матчей/день):
- Link + fixtures: ~100 запросов
- Team form: ~100 (50 матчей × 2 команды, кэш 24h)
- Lineups: ~100 (50 матчей)
- Post-match stats: ~50
- **Итого: ~350 запросов/день** из 7500 лимита. Остаток — резерв и доп. данные.

### The Odds API (100k кредитов/мес на плане $59)

Один запрос `GET /odds?sport=soccer_epl` возвращает **все матчи лиги** = 1 кредит × число букмекеров.

```python
# Экономия: запрашивать все матчи лиги одним запросом, не каждый матч отдельно
# Плохо:  for match in matches: get_odds(match_id)  → N кредитов
# Хорошо: get_odds(sport_key, regions='eu')          → 1 запрос, все матчи
```

---

## Приоритет заполнения (порядок разработки)

**Шаг 1 — Маппинг (миграции 011–015, 019):**
- `teams.logo_url` — заполняется автоматически при первой линковке
- `competitions` + `competition_external_ids`
- `match_external_ids` — авто-линковка матчей
- `match_odds` — коэффициенты для всех видов спорта

**Шаг 2 — Статистика football (миграции 016–018):**
- `match_stats` — после окончания матча
- `team_form` — 10 последних матчей команды
- `match_lineups` — за 1–2 часа до матча

**Шаг 3 — Аналитика (миграции 020–021):**
- `odds_history` — движение линий
- `ai_chat_cache` — pregenerated ответы Claude

---

## Пример: что AI получает на вход для прогноза по угловым

После интеграции в промпт для Claude попадает:

```
Match: Manchester City vs Arsenal | 2026-06-10 19:45 UTC | Premier League

TEAM FORM (last 5, corners):
Man City: 7,5,8,6,9 avg=7.0 | Opponent avg against: 4.2
Arsenal:  5,4,6,5,7 avg=5.4 | Opponent avg against: 5.8

H2H last 5:
2025-12-01: Man City 2-1 Arsenal | Corners: 9-4
2025-04-15: Arsenal 1-1 Man City | Corners: 6-7
...

CURRENT ODDS (corners market):
Over 9.5:  Bet365=1.87 | Pinnacle=1.91 | Unibet=1.85
Under 9.5: Bet365=1.94 | Pinnacle=1.90 | Unibet=1.96
Line movement: Over 9.5 dropped from 2.10 → 1.87 (-11%) — sharp action

EXPERT PREDICTIONS (from scraped sources):
[RO] beturi.ro: "Recomandăm Over 9.5 cornere @ 1.87" 
[RU] metaratings.ru: "Тоталы угловых: обе команды активны с флангов..."
```

Это несравнимо богаче чем просто текст прогноза — Claude даёт точный и обоснованный ответ.

# BetIQ — план оптимизации сервиса

Этот документ описывает конкретные изменения для оптимизации расхода API лимитов, очистки лишних данных и добавления управления загрузкой через админку.

---

## Контекст и проблемы

**Стек:** FastAPI + SQLAlchemy 2.0 (async) + APScheduler + Playwright. БД — PostgreSQL. Конфиг — `config.ini` + `.env`.

**Ключевые файлы:**
- `src/api_clients/jobs.py` — все фоновые задачи API
- `src/api_clients/odds_sync.py` — синхронизация The Odds API
- `src/api_clients/football_odds_sync.py` — синхронизация API-Football
- `src/api_clients/linker.py` — линкование матчей с внешними ID
- `src/api_clients/stats_sync.py` — статистика, составы, форма команд
- `src/scraper/scheduler.py` — APScheduler (cron расписание)
- `src/db/models.py` — ORM модели
- `config.ini` — параметры
- `alembic/versions/` — миграции (текущая голова `011`)

---

## Блок 1: Немедленные правки конфига

### 1.1 `config.ini` — сократить горизонты и частоты

```ini
[api_sync]
; Было 365 — тянули коэффициенты на год вперёд, теперь только 7 дней
odds_upcoming_days_ahead = 7

; Было 365 — теперь только ближайшая неделя
api_football_odds_days_ahead = 7

; Убрать расширенные рынки — каждый вызов /events/{id}/odds = отдельный кредит
; Было: btts,draw_no_bet,alternate_spreads,alternate_totals
odds_event_markets = btts

; Уменьшить батч fixture refresh
; Было 80 — 80 вызовов каждые 15 мин
fixture_refresh_limit = 20

; Уменьшить батч линкования
; Было 50
link_batch_size = 20
```

---

## Блок 2: Умный троттлинг в jobs.py

**Файл:** `src/api_clients/jobs.py`

### 2.1 Добавить временной буфер для синхронизации коэффициентов

Сейчас `job_fetch_odds()` запускается каждые 10 минут без проверки, нужна ли вообще синхронизация. Нужно добавить таблицу `api_sync_log` (или использовать Redis/in-memory dict) для хранения времени последнего успешного вызова по каждому `sport_key`.

**Логика:** не синхронизировать вид спорта, если последний успешный вызов был меньше 30 минут назад (конфигурируется).

```python
# В job_fetch_odds() перед циклом по sport_keys:
MIN_ODDS_INTERVAL_MINUTES = 30  # взять из config.ini как odds_min_interval_minutes

for sport_key in active_sport_keys:
    last_sync = await get_last_odds_sync_time(sport_key)  # новая функция
    if last_sync and (datetime.utcnow() - last_sync).total_seconds() < MIN_ODDS_INTERVAL_MINUTES * 60:
        logger.debug(f"Skipping odds sync for {sport_key}, last sync {last_sync}")
        continue
    await sync_odds_for_sport(sport_key)
    await save_odds_sync_time(sport_key)  # новая функция
```

Добавить в `config.ini`:
```ini
[api_sync]
odds_min_interval_minutes = 30
```

### 2.2 Активные виды спорта — только из матчей ближайших N дней

Сейчас перебираются все sport_keys из конфига. Нужно брать только те, для которых есть реальные матчи в БД в ближайшие `odds_upcoming_days_ahead` дней.

```python
# В jobs.py — функция получения активных sport_keys
async def get_active_sport_keys(db: AsyncSession, days_ahead: int) -> set[str]:
    cutoff = datetime.utcnow() + timedelta(days=days_ahead)
    result = await db.execute(
        select(Match.sport).distinct()
        .where(Match.match_date >= datetime.utcnow())
        .where(Match.match_date <= cutoff)
        .where(Match.status.notin_(["FT", "AET", "PEN", "CANC"]))
    )
    sports = {row[0] for row in result.fetchall()}
    # Маппинг sport → sport_key для The Odds API (из odds_keys.py)
    return {SPORT_TO_ODDS_KEY[s] for s in sports if s in SPORT_TO_ODDS_KEY}
```

### 2.3 Пропускать статистику и составы для незалинкованных матчей

В `stats_sync.py` — перед вызовом API проверять что `MatchExternalId` существует:

```python
# Пропустить матч если нет external_id для api_football
linked = await db.scalar(
    select(MatchExternalId.external_id)
    .where(MatchExternalId.match_id == match.id)
    .where(MatchExternalId.provider == "api_football")
)
if not linked:
    continue
```

---

## Блок 3: Фильтр рынков ставок при парсинге

**Файл:** `src/scraper/utils/normalizer.py` или место где `prediction_bets` сохраняются (`src/scraper/engine.py` или индивидуальные scrapers).

### 3.1 Разрешённые типы ставок

Добавить константу и фильтр перед INSERT в `prediction_bets`:

```python
# src/scraper/utils/normalizer.py
ALLOWED_BET_TYPES = frozenset({
    "1x2", "1X2", "winner",          # исход
    "total", "totals",               # тотал
    "both_teams_score", "btts",      # обе забьют
    "handicap",                      # гандикап
    "double_chance",                 # двойной шанс
    "draw_no_bet",                   # фора без ничьей
})

def is_allowed_bet_type(bet_type: str) -> bool:
    return bet_type.lower().strip() in {b.lower() for b in ALLOWED_BET_TYPES}
```

В движке при сохранении ставок:
```python
bets = [b for b in parsed_bets if is_allowed_bet_type(b.get("bet_type", ""))]
# Если нет разрешённых ставок — сохранять всё равно прогноз, просто без ставок
```

---

## Блок 4: Управление лигами в админке

### 4.1 Миграция — добавить поля управления в `competitions`

**Новая миграция** `alembic/versions/012_competition_tracking.py`:

```python
def upgrade():
    op.add_column("competitions", sa.Column("is_tracked", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("competitions", sa.Column("sync_odds", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("competitions", sa.Column("sync_stats", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("competitions", sa.Column("sync_lineups", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("competitions", sa.Column("odds_markets", sa.Text(), nullable=True))
    # JSON список рынков, например: ["h2h", "totals"]. NULL = использовать дефолт из config.ini
    op.add_column("competitions", sa.Column("odds_days_ahead", sa.Integer(), nullable=True))
    # NULL = использовать дефолт из config.ini

def downgrade():
    for col in ["is_tracked", "sync_odds", "sync_stats", "sync_lineups", "odds_markets", "odds_days_ahead"]:
        op.drop_column("competitions", col)
```

### 4.2 ORM модель — `src/db/models.py`

Добавить поля в класс `Competition`:

```python
class Competition(Base):
    # ... существующие поля ...
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_odds: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_stats: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_lineups: Mapped[bool] = mapped_column(Boolean, default=False)
    odds_markets: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-строка: '["h2h","totals"]' или NULL для дефолта
    odds_days_ahead: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL = брать из config.ini
```

### 4.3 API эндпоинты для управления лигами

**Файл:** `src/api/admin/` — добавить новый роутер `competitions.py`:

```
GET  /admin/api/competitions              — список всех лиг с полями is_tracked, sync_odds и т.д.
PATCH /admin/api/competitions/{id}        — обновить настройки лиги
POST /admin/api/competitions/{id}/sync-now — ручная принудительная синхронизация
GET  /admin/api/competitions/api-status   — текущие остатки квот API
```

**Pydantic схемы (добавить в схемы admin):**

```python
class CompetitionTrackingUpdate(BaseModel):
    is_tracked: bool | None = None
    sync_odds: bool | None = None
    sync_stats: bool | None = None
    sync_lineups: bool | None = None
    odds_markets: list[str] | None = None
    odds_days_ahead: int | None = None

class ApiQuotaStatus(BaseModel):
    the_odds_api_remaining: int | None
    the_odds_api_used: int | None
    api_football_remaining: int | None
    api_football_limit: int | None
    checked_at: datetime
```

### 4.4 Использовать настройки лиг в jobs

В `jobs.py` при выборке матчей для синхронизации коэффициентов:

```python
# Вместо: все матчи в ближайшие N дней
# Использовать: только матчи из отслеживаемых лиг
async def get_matches_for_odds_sync(db: AsyncSession) -> list[Match]:
    return await db.execute(
        select(Match)
        .join(Competition, Match.competition_id == Competition.id, isouter=True)
        .where(
            or_(
                Competition.sync_odds == True,        # лига явно включена
                Competition.id.is_(None),              # матч без лиги — синхронизировать по дефолту
            )
        )
        .where(Match.match_date >= datetime.utcnow())
        .where(Match.match_date <= datetime.utcnow() + timedelta(days=7))
        .where(Match.status.notin_(["FT", "AET", "PEN", "CANC"]))
    )
```

---

## Блок 5: Мониторинг квот API

### 5.1 Логировать остатки квоты после каждого вызова

**Файл:** `src/api_clients/the_odds_api.py`

После каждого успешного запроса сохранять в БД (или in-memory кэш):

```python
# В TheOddsApiClient после получения response:
remaining = response.headers.get("x-requests-remaining")
used = response.headers.get("x-requests-used")
if remaining:
    await save_quota_snapshot("the_odds_api", int(remaining), int(used or 0))

# Если remaining < 100 — отправить Telegram алерт
if remaining and int(remaining) < 100:
    await send_alert(f"⚠️ The Odds API: осталось {remaining} запросов!")
```

**Файл:** `src/api_clients/api_football.py`

API-Football возвращает квоту в теле ответа (`response['response']['requests']['current']`):

```python
# В ApiFootballClient при вызове get_account_status():
quota = data["response"]["requests"]
await save_quota_snapshot("api_football", 
    quota["limit"] - quota["current"], 
    quota["current"]
)
```

### 5.2 Новая таблица `api_quota_snapshots`

**Миграция** (добавить в `012` или отдельная `013`):

```python
op.create_table(
    "api_quota_snapshots",
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("provider", sa.String(50), nullable=False),  # the_odds_api | api_football
    sa.Column("requests_remaining", sa.Integer()),
    sa.Column("requests_used", sa.Integer()),
    sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
op.create_index("idx_quota_provider_time", "api_quota_snapshots", ["provider", "recorded_at"])
```

**ORM модель (`src/db/models.py`):**

```python
class ApiQuotaSnapshot(Base):
    __tablename__ = "api_quota_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    requests_remaining: Mapped[int | None] = mapped_column(Integer)
    requests_used: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

---

## Блок 6: Очистка устаревших данных

### 6.1 Добавить job очистки в `jobs.py`

```python
async def job_cleanup_old_data():
    """Запускать ежедневно в 03:00 UTC"""
    async with get_db_session() as db:
        cutoff_odds = datetime.utcnow() - timedelta(days=14)
        cutoff_quota = datetime.utcnow() - timedelta(days=30)
        
        # Удалить старую историю коэффициентов (движения линий)
        await db.execute(
            delete(OddsHistory).where(OddsHistory.recorded_at < cutoff_odds)
        )
        
        # Удалить старые снапшоты квоты
        await db.execute(
            delete(ApiQuotaSnapshot).where(ApiQuotaSnapshot.recorded_at < cutoff_quota)
        )
        
        # Удалить завершённые матчи из match_odds старше 7 дней
        await db.execute(
            delete(MatchOdds)
            .where(MatchOdds.match_id.in_(
                select(Match.id)
                .where(Match.match_date < datetime.utcnow() - timedelta(days=7))
                .where(Match.status.in_(["FT", "AET", "PEN", "CANC"]))
            ))
        )
        
        await db.commit()
```

Добавить в APScheduler (`scheduler.py`):
```python
scheduler.add_job(job_cleanup_old_data, "cron", hour=3, minute=0)
```

---

## Блок 7: UI в админке

### 7.1 Новая страница `/admin/competitions`

Это страница управления отслеживаемыми лигами. Реализовать в фронтенде (React/Next.js):

**Компоненты:**
1. **Таблица лиг** — колонки: Название, Вид спорта, Страна, Матчей, Трекинг, Коэффициенты, Статистика, Составы, Действия
2. **Строка редактирования** — toggle switches для каждого флага, input для `odds_days_ahead`
3. **Кнопка "Синх. сейчас"** — вызывает `POST /admin/api/competitions/{id}/sync-now`
4. **Панель квот** — вверху страницы, карточки с остатками The Odds API и API-Football

**Эндпоинт для таблицы:**
```
GET /admin/api/competitions?sport=football&is_tracked=true&page=1&limit=50
```

Ответ должен включать:
```json
{
  "items": [
    {
      "id": 1,
      "name": "Premier League",
      "sport": "football",
      "country": "England",
      "matches_upcoming": 12,
      "is_tracked": true,
      "sync_odds": true,
      "sync_stats": false,
      "sync_lineups": true,
      "odds_markets": ["h2h", "totals"],
      "odds_days_ahead": 7
    }
  ],
  "total": 120,
  "quota": {
    "the_odds_api_remaining": 4200,
    "api_football_remaining": 87
  }
}
```

### 7.2 Расширить страницу `/admin/sources`

Добавить к каждому источнику:
- **Привязка к лигам** — multiselect: для каких лиг парсить (если пусто — парсить всё)
- **Разрешённые виды спорта** — фильтр на уровне источника

Это реализуется через новую связующую таблицу `source_competition_filters`:
```sql
CREATE TABLE source_competition_filters (
    source_id INT REFERENCES sources(id) ON DELETE CASCADE,
    competition_id INT REFERENCES competitions(id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, competition_id)
);
```

Если у источника нет записей в этой таблице — парсить всё (текущее поведение, обратная совместимость).

---

## Порядок реализации

| # | Задача | Файлы | Приоритет |
|---|--------|-------|-----------|
| 1 | Изменить конфиг — `odds_upcoming_days_ahead = 7`, `api_football_odds_days_ahead = 7`, убрать `alternate_*` рынки | `config.ini` | Критично |
| 2 | Миграция 012: добавить поля в `competitions` + таблицу `api_quota_snapshots` | `alembic/versions/012_*` | Высокий |
| 3 | Обновить ORM модели | `src/db/models.py` | Высокий |
| 4 | Добавить троттлинг в `job_fetch_odds()` — пропускать если < 30 мин с последней синхронизации | `src/api_clients/jobs.py` | Высокий |
| 5 | Логировать квоту после каждого вызова The Odds API и API-Football | `src/api_clients/the_odds_api.py`, `src/api_clients/api_football.py` | Высокий |
| 6 | Фильтр `ALLOWED_BET_TYPES` при сохранении ставок из парсеров | `src/scraper/utils/normalizer.py`, `src/scraper/engine.py` | Средний |
| 7 | Использовать `competition.sync_odds` при выборке матчей для jobs | `src/api_clients/jobs.py` | Средний |
| 8 | Добавить эндпоинты управления лигами в Admin API | `src/api/admin/competitions.py` | Средний |
| 9 | Добавить `job_cleanup_old_data()` в scheduler | `src/api_clients/jobs.py`, `src/scraper/scheduler.py` | Средний |
| 10 | UI страница `/admin/competitions` | фронтенд | Низкий |
| 11 | Таблица `source_competition_filters` + UI привязки | миграция + фронтенд | Низкий |

---

## Ожидаемый эффект

| Изменение | Снижение нагрузки |
|-----------|-------------------|
| `odds_upcoming_days_ahead` 365 → 7 | ~90% меньше вызовов The Odds API |
| Убрать `alternate_*` markets | ~50% меньше event-level вызовов |
| Троттлинг 10 мин → 30 мин | ~66% меньше вызовов |
| `fixture_refresh_limit` 80 → 20 | ~75% меньше API-Football fixture calls |
| `link_batch_size` 50 → 20 | ~60% меньше вызовов линкования |
| Фильтр bet_types | ~60% меньше строк в `prediction_bets` |

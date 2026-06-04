# План: визуальная админка BetIQ

## Этап 1 — Справочник команд (✓ в работе)
- Таблица `teams`: `normalized_key`, `display_name`, `sport`, `logo_path`, `aliases`
- У `matches`: `team_home_id`, `team_away_id` (FK)
- При сохранении прогноза — `get_or_create_team()` для обеих сторон
- Миграция + backfill из существующих матчей

## Этап 2 — Admin API (`/api/admin/v1`)
- Авторизация: заголовок `X-Admin-Key` = `ADMIN_API_KEY` из `.env`
- **Матчи**: список с фильтрами (спорт, даты, поиск по команде), деталь с прогнозами
- **Команды**: CRUD, загрузка логотипа (`POST .../logo`)
- **AI**: список матчей со сводками, перегенерация, просмотр шаблона промпта
- **Настройки**: чтение `config.ini`, источники, статус scheduler (логи)
- **Действия**: health check / diagnose / scrape / AI по кнопке (фоновый subprocess)

## Этап 3 — Frontend (`admin-ui/`)
- React + Vite + TypeScript
- Разделы: Матчи | Команды | AI | Настройки
- Таблицы с фильтрами, формы редактирования

## Этап 4 — Деплой
- `npm run build` → `admin-ui/dist`
- FastAPI: `/admin` — SPA, `/uploads` — картинки команд
- Документация в `instructions/admin.md`

## Этап 5 (✓)
- **Карточка матча** `/admin/matches/:id` — полный текст прогнозов (`full_text`), ставки, AI-сводка
- **Дубликаты команд** — `GET /teams/duplicates`, `POST /teams/merge`, `POST /teams/merge-auto`

## Дальше
- Редактирование `.env` и `proxies.txt` через UI (осторожно с секретами)
- Роли пользователей, audit log
- WebSocket для live-логов парсера

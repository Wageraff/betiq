-- Сброс прогнозов legalbet и мусорных матчей, затем перезапустите:
-- ./venv/bin/python3.11 -m src.scraper.engine --source legalbet --limit 50

BEGIN;

DELETE FROM prediction_bets
WHERE prediction_id IN (
  SELECT id FROM predictions WHERE source_url LIKE '%legalbet.ro%'
);

DELETE FROM predictions WHERE source_url LIKE '%legalbet.ro%';

-- Дубликаты и битый парсинг (подставьте свои id при необходимости)
DELETE FROM matches
WHERE id IN (7, 8, 9, 14, 15, 20, 22, 23)
   OR team_home ILIKE '%PONTURI PARIURI%'
   OR team_away ~* 'IUNIE 20[0-9]{2}'
   OR team_away ILIKE '%: Ponturi%'
   OR slug LIKE '%ponturipariuri%'
   OR slug LIKE '%felixauger-vs-aliassime%';

-- Сироты без прогнозов
DELETE FROM matches m
WHERE NOT EXISTS (SELECT 1 FROM predictions p WHERE p.match_id = m.id);

COMMIT;

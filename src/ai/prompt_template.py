"""Загрузка и подстановка переменных в шаблон AI-промпта."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.config import BASE_DIR, settings
from src.db.models import Match, Prediction

log = logging.getLogger("ai.prompt")

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_DEFAULT_TEMPLATE = BASE_DIR / "prompts" / "ai_match_summary.txt"


def resolve_prompt_path() -> Path:
    raw = (settings.ai_prompt_template or "").strip()
    if not raw:
        return _DEFAULT_TEMPLATE
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def load_prompt_template() -> str:
    path = resolve_prompt_path()
    if not path.is_file():
        raise FileNotFoundError(f"AI prompt template not found: {path}")
    text = path.read_text(encoding="utf-8")
    log.debug("Loaded AI prompt template: %s (%s chars)", path, len(text))
    return text


def format_predictions_block(
    predictions: list[Prediction],
    *,
    analysis_max_chars: int = 500,
) -> str:
    blocks: list[str] = []
    for p in predictions:
        source_name = p.source.name if p.source else "unknown"
        bets_str = ", ".join(
            f"{b.bet_pick} @ {b.odds}"
            for b in sorted(p.bets, key=lambda x: x.sort_order)
            if b.bet_pick or b.odds is not None
        )
        analysis = (p.full_text or "")[:analysis_max_chars]
        blocks.append(
            f"Source: {source_name} ({p.language})\n"
            f"Bets: {bets_str or 'n/a'}\n"
            f"Analysis: {analysis}\n---"
        )
    return "\n".join(blocks) if blocks else "(no predictions)"


def build_prompt_variables(match: Match, predictions: list[Prediction]) -> dict[str, str]:
    match_date = ""
    if match.match_date:
        dt = match.match_date
        if dt.tzinfo:
            match_date = dt.isoformat()
        else:
            match_date = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "team_home": match.team_home or "",
        "team_away": match.team_away or "",
        "match_title": f"{match.team_home} vs {match.team_away}",
        "match_date": match_date,
        "competition": match.competition or "N/A",
        "sport": match.sport or "N/A",
        "predictions_count": str(len(predictions)),
        "predictions_block": format_predictions_block(
            predictions, analysis_max_chars=settings.ai_analysis_max_chars
        ),
        "slug": match.slug or "",
    }


def render_prompt_template(template: str, variables: dict[str, str]) -> str:
    unknown: set[str] = set()

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in variables:
            unknown.add(key)
            return m.group(0)
        return variables[key]

    out = _PLACEHOLDER_RE.sub(repl, template)
    if unknown:
        log.warning("Unknown placeholders in AI template (left as-is): %s", sorted(unknown))
    return out


def build_match_summary_prompt(match: Match, predictions: list[Prediction]) -> str:
    template = load_prompt_template()
    variables = build_prompt_variables(match, predictions)
    return render_prompt_template(template, variables)

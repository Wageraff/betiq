"""Клавиатуры Telegram-бота."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from src.db.models import Match, Source

MENU_DASHBOARD = "📊 Dashboard"
MENU_SOURCES = "📋 Источники"
MENU_LOGS = "📜 Логи"
MENU_DIAGNOSE = "🔍 Diagnose"
MENU_SCRAPE = "▶️ Парсинг"
MENU_AI = "🤖 AI"
MENU_SERVICE = "🛠 Сервис"
MENU_HELP = "ℹ️ Help"

MENU_BUTTONS = (
    MENU_DASHBOARD,
    MENU_SOURCES,
    MENU_LOGS,
    MENU_DIAGNOSE,
    MENU_SCRAPE,
    MENU_AI,
    MENU_SERVICE,
    MENU_HELP,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MENU_DASHBOARD), KeyboardButton(MENU_SOURCES)],
            [KeyboardButton(MENU_LOGS), KeyboardButton(MENU_DIAGNOSE)],
            [KeyboardButton(MENU_SCRAPE), KeyboardButton(MENU_AI)],
            [KeyboardButton(MENU_SERVICE), KeyboardButton(MENU_HELP)],
        ],
        resize_keyboard=True,
    )


def service_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Health check", callback_data="menu:service:health"),
                InlineKeyboardButton("Repair catalog", callback_data="menu:service:repair"),
            ],
            [
                InlineKeyboardButton("Log info", callback_data="menu:service:loginfo"),
                InlineKeyboardButton("Log tail (40)", callback_data="menu:service:logtail"),
            ],
            [
                InlineKeyboardButton("Morning digest", callback_data="menu:service:digest"),
            ],
        ]
    )


def sources_inline_keyboard(
    sources: list[Source],
    *,
    prefix: str,
    show_all: bool = True,
) -> InlineKeyboardMarkup:
    """prefix: menu:scrape или menu:diagnose"""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for s in sources:
        if not s.scraper_module:
            continue
        mod = s.scraper_module
        label = (s.name or mod)[:20]
        row.append(
            InlineKeyboardButton(label, callback_data=f"{prefix}:{mod}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if show_all and prefix == "menu:scrape":
        rows.append(
            [InlineKeyboardButton("All active", callback_data="menu:scrape:all")]
        )
    return InlineKeyboardMarkup(rows)


def ai_matches_keyboard(matches: list[Match]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in matches[:10]:
        title = f"{m.team_home} vs {m.team_away}"[:28]
        rows.append(
            [
                InlineKeyboardButton(
                    f"▶ {title}",
                    callback_data=f"menu:ai:{m.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)

"""Приоритеты источников для quick/full scrape."""
from __future__ import annotations

from enum import Enum

from src.config import source_tier_high, source_tier_low, source_tier_medium


class ScrapeTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def tier_for_module(module: str | None) -> ScrapeTier:
    if not module:
        return ScrapeTier.MEDIUM
    if module in source_tier_high:
        return ScrapeTier.HIGH
    if module in source_tier_low:
        return ScrapeTier.LOW
    if module in source_tier_medium:
        return ScrapeTier.MEDIUM
    return ScrapeTier.MEDIUM


def include_in_quick(module: str | None) -> bool:
    return tier_for_module(module) != ScrapeTier.LOW

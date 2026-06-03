"""Реестр модулей источников по имени scraper_module."""
from __future__ import annotations

import importlib
from types import ModuleType

SOURCE_MODULES = {
    "beturi": "src.scraper.sources.beturi",
    "pontulzilei": "src.scraper.sources.pontulzilei",
    "legalbet": "src.scraper.sources.legalbet",
}


def load_source_module(name: str) -> ModuleType:
    path = SOURCE_MODULES.get(name)
    if not path:
        raise ValueError(f"Unknown scraper module: {name}")
    return importlib.import_module(path)

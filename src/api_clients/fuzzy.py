"""Fuzzy match названий команд."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def _norm(name: str) -> str:
    text = (name or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text)


def fuzzy_match(a: str, b: str, *, threshold: float = 0.72) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # Короткие имена (< 8 символов) чаще дают ложные совпадения — повышаем порог
    if min(len(na), len(nb)) < 8:
        threshold = max(threshold, 0.85)
    return SequenceMatcher(None, na, nb).ratio() >= threshold

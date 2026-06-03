"""Пул прокси с round-robin и временной баной (из reference_scraper)."""
from __future__ import annotations

import logging
import random
import re
import threading
import time
from typing import Optional
from urllib.parse import urlparse

from src.config import load_proxies

log = logging.getLogger("proxy_pool")

_AREA_RE = re.compile(r"area-[a-z]{2}", re.I)


def apply_proxy_geo(proxy: str, geo: Optional[str]) -> str:
    """
    Smartproxy: в username подставляется area-XX (например area-RO → area-RU).
    Если area-* в строке нет — возвращаем прокси без изменений.
    """
    if not proxy or not geo:
        return proxy
    code = geo.strip().upper()[:2]
    if not _AREA_RE.search(proxy):
        return proxy
    return _AREA_RE.sub(f"area-{code}", proxy, count=1)


class ProxyPool:
    BAN_SECONDS = 300

    def __init__(self) -> None:
        self._proxies = load_proxies()
        self._lock = threading.Lock()
        self._banned: dict[str, float] = {}
        self._idx = random.randint(0, max(len(self._proxies) - 1, 0)) if self._proxies else 0
        if self._proxies:
            log.info("Loaded proxies: %s", len(self._proxies))
        else:
            log.warning("No proxies configured")

    def get(self, geo: Optional[str] = None) -> Optional[str]:
        with self._lock:
            if not self._proxies:
                return None
            now = time.time()
            self._banned = {p: t for p, t in self._banned.items() if t > now}
            available = [p for p in self._proxies if p not in self._banned]
            if not available:
                base = random.choice(self._proxies)
            else:
                base = available[self._idx % len(available)]
                self._idx += 1
            return apply_proxy_geo(base, geo)

    def _base_proxy(self, proxy: str) -> str:
        """Строка из proxies.txt, соответствующая выданному прокси (с любым area-XX)."""
        for p in self._proxies:
            if self._same_endpoint(p, proxy):
                return p
        return proxy

    @staticmethod
    def _same_endpoint(a: str, b: str) -> bool:
        pa, pb = urlparse(a), urlparse(b)
        ua = _AREA_RE.sub("", pa.username or "")
        ub = _AREA_RE.sub("", pb.username or "")
        return (
            pa.hostname == pb.hostname
            and pa.port == pb.port
            and ua == ub
            and pa.password == pb.password
        )

    def report_failure(self, proxy: str) -> None:
        if not proxy:
            return
        with self._lock:
            base = self._base_proxy(proxy)
            self._banned[base] = time.time() + self.BAN_SECONDS
            log.warning("Proxy banned for %ss: %s", self.BAN_SECONDS, self._mask(proxy))

    @staticmethod
    def _mask(proxy: str) -> str:
        try:
            p = urlparse(proxy)
            return f"{p.scheme}://***@{p.hostname}:{p.port}"
        except Exception:
            return "***"

    @staticmethod
    def to_playwright(proxy):
        if not proxy:
            return None
        p = urlparse(proxy)
        out: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
        if p.username:
            out["username"] = p.username
        if p.password:
            out["password"] = p.password
        return out

    @property
    def has_proxies(self) -> bool:
        return bool(self._proxies)

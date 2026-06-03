"""Пул прокси с round-robin и временной баной."""
import logging
import random
import threading
import time
from urllib.parse import urlparse

from .settings import load_proxies

log = logging.getLogger("proxy_pool")


class ProxyPool:
    BAN_SECONDS = 300

    def __init__(self):
        self._proxies = load_proxies()
        self._lock = threading.Lock()
        self._banned: dict[str, float] = {}
        self._idx = 0
        if self._proxies:
            log.info(f"Загружено прокси: {len(self._proxies)}")
        else:
            log.warning("⚠ Прокси не настроены!")

    def get(self) -> str | None:
        with self._lock:
            if not self._proxies:
                return None
            now = time.time()
            self._banned = {p: t for p, t in self._banned.items() if t > now}
            available = [p for p in self._proxies if p not in self._banned]
            if not available:
                return random.choice(self._proxies)
            proxy = available[self._idx % len(available)]
            self._idx += 1
            return proxy

    def report_failure(self, proxy: str):
        if not proxy:
            return
        with self._lock:
            self._banned[proxy] = time.time() + self.BAN_SECONDS
            log.warning(f"Прокси забанен на {self.BAN_SECONDS}с: {self._mask(proxy)}")

    @staticmethod
    def _mask(proxy: str) -> str:
        try:
            p = urlparse(proxy)
            return f"{p.scheme}://***@{p.hostname}:{p.port}"
        except Exception:
            return "***"

    @staticmethod
    def to_playwright(proxy: str) -> dict | None:
        if not proxy:
            return None
        p = urlparse(proxy)
        out = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
        if p.username:
            out["username"] = p.username
        if p.password:
            out["password"] = p.password
        return out

    @property
    def has_proxies(self) -> bool:
        return bool(self._proxies)

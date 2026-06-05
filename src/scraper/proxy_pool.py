"""Пул Smartproxy: sticky session на источник (вариант B), бан и ротация на spare."""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional
from urllib.parse import quote, unquote, urlparse, urlunparse

from src.config import load_proxies, load_proxy_sessions

log = logging.getLogger("proxy_pool")

_AREA_RE = re.compile(r"area-[a-z]{2}", re.I)
_SESSION_RE = re.compile(r"session-[^_]+", re.I)


def apply_proxy_geo(proxy: str, geo: Optional[str]) -> str:
    """Подставить area-XX в username по geo источника."""
    if not proxy or not geo:
        return proxy
    code = geo.strip().upper()[:2]
    p = urlparse(proxy)
    user = p.username or ""
    if not _AREA_RE.search(user):
        return proxy
    user = _AREA_RE.sub(f"area-{code}", user, count=1)
    return urlunparse(p._replace(username=user))


def _inject_session(username: str, session: str) -> str:
    session = session.strip()
    if not session.startswith("session-"):
        session = f"session-{session}"
    if _SESSION_RE.search(username):
        return _SESSION_RE.sub(session, username, count=1)
    return f"{username}_{session}" if username else session


def build_proxy_url(base: str, session: str, geo: Optional[str]) -> str:
    """Собрать URL прокси: session + area-{geo} в username."""
    p = urlparse(base)
    user = _inject_session(p.username or "", session)
    return apply_proxy_geo(urlunparse(p._replace(username=user)), geo)


class ProxyPool:
    BAN_SECONDS = 300

    def __init__(self) -> None:
        self._proxies = load_proxies()
        self._sessions = load_proxy_sessions()
        self._lock = threading.Lock()
        self._banned: dict[str, float] = {}
        # source_module → активный session (после ротации при бане)
        self._session_override: dict[str, str] = {}
        if self._proxies:
            log.info(
                "Loaded proxies: %s lines, source sessions: %s",
                len(self._proxies),
                len(self._sessions),
            )
        else:
            log.warning("No proxies configured")

    def _template_proxy(self) -> str:
        return self._proxies[0]

    def _session_for_source(self, source_module: Optional[str]) -> Optional[str]:
        if not source_module:
            return None
        if source_module in self._session_override:
            return self._session_override[source_module]
        return self._sessions.get(source_module)

    def _find_line_for_session(self, session_id: str) -> Optional[str]:
        needle = session_id if session_id.startswith("session-") else f"session-{session_id}"
        for proxy in self._proxies:
            user = urlparse(proxy).username or ""
            if needle.lower() in user.lower():
                return proxy
        return None

    def _all_session_ids(self) -> list[str]:
        ids: list[str] = []
        for proxy in self._proxies:
            user = urlparse(proxy).username or ""
            m = _SESSION_RE.search(user)
            if m:
                ids.append(m.group(0).replace("session-", ""))
        return ids

    def _pick_spare_session(self, source_module: str, geo: Optional[str]) -> Optional[str]:
        assigned = set(self._sessions.values())
        overrides = set(self._session_override.values())
        now = time.time()
        for proxy in self._proxies:
            user = urlparse(proxy).username or ""
            m = _SESSION_RE.search(user)
            if not m:
                continue
            sid = m.group(0).replace("session-", "")
            if sid in assigned and self._session_override.get(source_module) != sid:
                if source_module in self._sessions and sid == self._sessions[source_module]:
                    continue
            base_key = self._ban_key(proxy)
            if self._banned.get(base_key, 0) > now:
                continue
            if geo and _AREA_RE.search(user):
                code = geo.strip().upper()[:2]
                if f"area-{code.lower()}" not in user.lower():
                    # area подставится при apply_proxy_geo
                    pass
            return sid
        for sid in self._all_session_ids():
            if sid not in assigned and sid not in overrides:
                return sid
        return None

    def _ban_key(self, proxy: str) -> str:
        p = urlparse(proxy)
        user = _SESSION_RE.sub("session-*", p.username or "")
        user = _AREA_RE.sub("area-*", user)
        return f"{p.hostname}:{p.port}:{user}"

    def get(
        self,
        geo: Optional[str] = None,
        *,
        source_module: Optional[str] = None,
    ) -> Optional[str]:
        """Прокси для источника: фиксированный session из config (вариант B)."""
        with self._lock:
            if not self._proxies:
                return None

            session_id = self._session_for_source(source_module)
            if session_id:
                line = self._find_line_for_session(session_id) or self._template_proxy()
                proxy = build_proxy_url(line, session_id, geo)
                log.debug(
                    "Proxy for %s: %s geo=%s",
                    source_module,
                    _SESSION_RE.search(urlparse(proxy).username or ""),
                    geo,
                )
                return proxy

            # fallback: первая строка + geo (health без source)
            return apply_proxy_geo(self._template_proxy(), geo)

    def seconds_until_available(self) -> float:
        with self._lock:
            if not self._proxies:
                return 0.0
            now = time.time()
            if any(self._banned.get(self._ban_key(p), 0) <= now for p in self._proxies):
                return 0.0
            if not self._banned:
                return 0.0
            return max(0.0, min(self._banned.values()) - now)

    def report_failure(
        self,
        proxy: str,
        *,
        source_module: Optional[str] = None,
    ) -> None:
        if not proxy:
            return
        with self._lock:
            key = self._ban_key(proxy)
            self._banned[key] = time.time() + self.BAN_SECONDS
            log.warning(
                "Proxy banned for %ss (source=%s): %s",
                self.BAN_SECONDS,
                source_module or "?",
                self._mask(proxy),
            )
            if source_module:
                spare = self._pick_spare_session(source_module, None)
                if spare and spare != self._session_for_source(source_module):
                    self._session_override[source_module] = spare
                    log.warning(
                        "Source %s: rotate proxy session -> %s",
                        source_module,
                        spare,
                    )

    @staticmethod
    def _mask(proxy: str) -> str:
        try:
            p = urlparse(proxy)
            user = p.username or ""
            m = _SESSION_RE.search(user)
            tag = m.group(0) if m else "session-?"
            return f"{p.scheme}://{tag}:***@{p.hostname}:{p.port}"
        except Exception:
            return "***"

    @staticmethod
    def to_playwright(proxy: str) -> dict | None:
        """Формат для Playwright new_context: только server, auth в URL.

        Отдельные username/password в per-context proxy дают
        «Got unexpected field names: ['username']» на Chromium.
        """
        if not proxy:
            return None
        p = urlparse(proxy)
        scheme = p.scheme or "http"
        host = p.hostname or ""
        port = p.port
        if not host:
            return None
        server = f"{scheme}://{host}:{port}"
        if p.username:
            user = quote(unquote(p.username), safe="")
            pw = quote(unquote(p.password or ""), safe="")
            server = f"{scheme}://{user}:{pw}@{host}:{port}"
        return {"server": server}

    @property
    def has_proxies(self) -> bool:
        return bool(self._proxies)

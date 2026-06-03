"""Очистка HTML статей для SEO/хранения."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

_ALLOWED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "strong",
    "em",
    "b",
    "i",
    "br",
    "blockquote",
}

_STRIP_TAGS = {"script", "style", "iframe", "svg", "form", "button", "nav", "aside"}


def html_to_plain_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


def clean_article_html(html: str) -> str:
    """Заголовки, списки, таблицы, параграфы; без атрибутов и внешних ссылок."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.startswith(("http://", "https://", "//")):
            a.replace_with(NavigableString(a.get_text(" ", strip=True)))
        else:
            a.unwrap()

    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        tag.attrs = {}

    out = str(soup).strip()
    return re.sub(r">\s+<", ">\n<", out)

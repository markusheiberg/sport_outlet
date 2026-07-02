"""Scraper for xxl.no.

XXL's catalog data comes from the Apptus eSales storefront API
(*.api.esales.apptus.cloud, "landing-page" query). Its URL carries
per-visitor customerKey/sessionKey values, so the API is never called
directly; instead we load a category page in the browser and intercept
the site's own API response. Its navigation tree contains a node
{path: "/", label: "All", count: <N>} with the site-wide article total
(verified in the Network tab: 23246).

Per-category counts use the "Artikler: <N>" label rendered on every
category page (verified live: Dame shows "Artikler: 4228"). Category
URLs (e.g. /dame/c/9200000) are resolved from the homepage top
navigation by visible link text - never guessed.
"""
from __future__ import annotations

import json
import re
import unicodedata

from playwright.sync_api import Page

from ._common import ScrapeError, dismiss_cookie_banner

HOME_URL = "https://www.xxl.no/"

# Top-navigation product categories. "Kampanjer" and "Varemerker" are
# campaign/brand listings, not categories, and are deliberately excluded.
CATEGORY_NAMES = [
    "Dame",
    "Herre",
    "Barn",
    "Sykkel",
    "Sport",
    "Løping",
    "Turutstyr",
    "Jakt & Fiske",
    "Vannsport",
    "Outlet",
]

_ARTICLES_RE = re.compile(r"Artikler:\s*([\d][\d  .]*)")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().casefold()


def _find_all_count(node) -> int | None:
    """Locate {path: "/", label: "All", count: int} anywhere in a JSON tree."""
    if isinstance(node, dict):
        if (
            node.get("path") == "/"
            and node.get("label") == "All"
            and isinstance(node.get("count"), int)
        ):
            return node["count"]
        for value in node.values():
            found = _find_all_count(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_all_count(value)
            if found is not None:
                return found
    return None


def get_categories(page: Page) -> dict[str, str]:
    """Category name -> URL from the homepage top navigation."""
    wanted = {_norm(name): name for name in CATEGORY_NAMES}
    page.goto(HOME_URL, wait_until="domcontentloaded")
    dismiss_cookie_banner(page)
    page.wait_for_timeout(2000)
    anchors = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
    )
    resolved: dict[str, str] = {}
    for anchor in anchors:
        key = _norm(anchor["text"])
        if key in wanted and wanted[key] not in resolved and "/c/" in anchor["href"]:
            resolved[wanted[key]] = anchor["href"]
    if not resolved:
        raise ScrapeError(f"no category links found in the top navigation of {HOME_URL}")
    return resolved


def get_sku_count(page: Page, start_url: str | None = None) -> int:
    if start_url is None:
        return _total_from_api(page)
    return _article_count_from_page(page, start_url)


def _total_from_api(page: Page) -> int:
    """Site-wide article count from the navigation tree's "All" node,
    intercepted from the site's own eSales API call on a category page
    (the landing-page/PLP query only fires there, not on the homepage).
    """
    found: list[int] = []

    def on_response(response) -> None:
        if "apptus.cloud" not in response.url or found:
            return
        try:
            data = response.json()
        except Exception:
            return
        count = _find_all_count(data)
        if count is not None:
            found.append(count)

    page.on("response", on_response)
    try:
        categories = get_categories(page)
        first_url = next(iter(categories.values()))
        page.goto(first_url, wait_until="domcontentloaded")
        for _ in range(60):
            if found:
                break
            page.wait_for_timeout(500)
    finally:
        page.remove_listener("response", on_response)

    if not found:
        raise ScrapeError(
            "no eSales API response with an All-node count seen on " + page.url
        )
    return found[0]


def _article_count_from_page(page: Page, url: str) -> int:
    """Read the rendered "Artikler: <N>" label on a category page."""
    page.goto(url, wait_until="domcontentloaded")
    dismiss_cookie_banner(page)
    try:
        page.wait_for_selector("text=Artikler", timeout=30_000)
    except Exception:
        raise ScrapeError(f"no 'Artikler' label appeared within 30s at {page.url}")
    match = _ARTICLES_RE.search(page.inner_text("body"))
    if not match:
        raise ScrapeError(f"could not parse 'Artikler: N' text at {page.url}")
    return int(re.sub(r"\D", "", match.group(1)))

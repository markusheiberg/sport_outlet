"""Scraper for sportoutlet.no.

`/campaign` is the full "browse all" catalog (breadcrumb: Hjem > Alle) -
Sport Outlet is an outlet store, so every listed item legitimately carries
a "Siste sjanse!" (last chance) badge; that's not a clearance-only filter.
The catalog has no URL pagination - all products load via infinite scroll.

Each product tile has an <img alt="Image of product: ..."> whose `src` is
a CDN URL of the form:
  https://cdn.gets.no/feed-so/articles/<article-id>/<image-id>_200.png
The <article-id> segment is stable per product and used as the dedupe key
(product *name*/alt text is not unique - color/size variants share it).

Category pages (e.g. https://sportoutlet.no/kl%C3%A6r) use the same tile
markup and infinite scroll. Their URLs are resolved from the live DOM by
matching visible link text against CATEGORY_NAMES rather than hardcoding
slugs, so multi-word categories can't be mis-guessed. A product can appear
in more than one category, so the per-category counts may sum to more than
the "all" count.
"""
from __future__ import annotations

import unicodedata

from playwright.sync_api import Page

from ._common import ScrapeError, count_unique_elements_by_scroll, dismiss_cookie_banner

START_URL = "https://sportoutlet.no/campaign"
HOME_URL = "https://sportoutlet.no/"
PRODUCT_IMAGE_SELECTOR = 'img[alt^="Image of product:"]'
ARTICLE_ID_PATTERN = r"/articles/[^/]+/"

# Top-level categories in the "Kategori" filter menu on /campaign.
CATEGORY_NAMES = [
    "Klær",
    "Sko",
    "Friluft og camping",
    "Sportsutstyr",
    "Trimutstyr",
    "Fiskeutstyr",
    "Mat og drikke",
    "Vintersport",
    "Lagsport",
    "Sykkel",
    "Kjæledyr",
]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().casefold()


def _collect_links(page: Page) -> dict[str, str]:
    """Map normalized visible link text -> absolute href for all anchors."""
    anchors = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
    )
    return {_norm(a["text"]): a["href"] for a in anchors if a["text"]}


def _merge_matching_links(page: Page, wanted: dict[str, str], resolved: dict[str, str]) -> None:
    links = _collect_links(page)
    for key, name in wanted.items():
        if name not in resolved and key in links:
            resolved[name] = links[key]


def _open_panel(page: Page, label: str) -> bool:
    """Click a toggle like 'Kategori' or 'Meny'; True if it was clicked."""
    try:
        toggle = page.get_by_text(label, exact=True).first
        if toggle.is_visible(timeout=1500):
            toggle.click(timeout=2000)
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


def get_categories(page: Page) -> dict[str, str]:
    """Resolve category name -> URL from the live DOM (no guessed slugs).

    Strategy 1: find anchors whose visible text is a category name, also
    after opening the Kategori filter and the Meny drawer.
    Strategy 2 (fallback, since the Kategori items may be JS-navigating
    buttons rather than <a> tags): click each category name and capture
    the URL the site itself navigates to.
    """
    wanted = {_norm(name): name for name in CATEGORY_NAMES}
    resolved: dict[str, str] = {}

    for url in (START_URL, HOME_URL):
        page.goto(url, wait_until="domcontentloaded")
        dismiss_cookie_banner(page)
        page.wait_for_timeout(2000)
        _merge_matching_links(page, wanted, resolved)
        for label in ("Kategori", "Meny"):
            if _open_panel(page, label):
                _merge_matching_links(page, wanted, resolved)
        if len(resolved) == len(wanted):
            return resolved

    for key, name in wanted.items():
        if name in resolved:
            continue
        try:
            page.goto(START_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            item = page.get_by_text(name, exact=True).first
            if not item.is_visible(timeout=1500):
                _open_panel(page, "Kategori")
                item = page.get_by_text(name, exact=True).first
                if not item.is_visible(timeout=1500):
                    continue
            item.click(timeout=2000)
            page.wait_for_timeout(2500)
            if page.url.rstrip("/") != START_URL.rstrip("/"):
                resolved[name] = page.url
        except Exception:
            continue

    if not resolved:
        raise ScrapeError(
            f"could not resolve any category links on {START_URL} or {HOME_URL}"
        )
    return resolved


def get_sku_count(page: Page, start_url: str = START_URL) -> int:
    return count_unique_elements_by_scroll(
        page,
        start_url=start_url,
        selector=PRODUCT_IMAGE_SELECTOR,
        attribute="src",
        key_pattern=ARTICLE_ID_PATTERN,
    )

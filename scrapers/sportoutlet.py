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
markup and infinite scroll, but their URL slugs are SCRAMBLED relative to
their content: /kj%C3%A6ledyr actually serves the Klær category (its
<title> is "Alle produkter i Klær - Klær | Sport Outlet") while its <h1>
misleadingly echoes the slug. Category URLs are therefore resolved by
probing candidates and letting each page identify itself via the title
pattern / breadcrumb self-link - never by slug text or <h1>. A product
can appear in more than one category, so per-category counts may sum to
more than the "all" count.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse

from playwright.sync_api import Page

from ._common import ScrapeError, count_unique_elements_by_scroll, dismiss_cookie_banner

START_URL = "https://sportoutlet.no/campaign"
HOME_URL = "https://sportoutlet.no/"
CATEGORIES_API_URL = "https://sportoutlet.no/api/v1/categories"
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


# Key names commonly used for a display name / link target in category
# JSON payloads; matched entries are still filtered against CATEGORY_NAMES.
_API_NAME_KEYS = ("name", "title", "label")
_API_URL_KEYS = ("url", "href", "link", "path", "slug")


def _walk_category_entries(node):
    """Yield (name, absolute_url) for every dict in a JSON tree that has
    both a name-ish and a url-ish string field, regardless of nesting."""
    if isinstance(node, dict):
        name = next(
            (node[k].strip() for k in _API_NAME_KEYS
             if isinstance(node.get(k), str) and node[k].strip()),
            None,
        )
        url = next(
            (node[k].strip() for k in _API_URL_KEYS
             if isinstance(node.get(k), str) and node[k].strip()),
            None,
        )
        if name and url:
            yield name, urllib.parse.urljoin(HOME_URL, url)
        for value in node.values():
            yield from _walk_category_entries(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_category_entries(value)


def _categories_from_api(page: Page, wanted: dict[str, str]) -> dict[str, str]:
    """name -> URL for wanted categories, from the site's own categories
    API. Returns whatever subset it could resolve; empty dict on failure."""
    resolved: dict[str, str] = {}
    try:
        response = page.request.get(CATEGORIES_API_URL)
        if not response.ok:
            return resolved
        data = response.json()
    except Exception:
        return resolved
    for name, url in _walk_category_entries(data):
        key = _norm(name)
        if key in wanted and wanted[key] not in resolved:
            resolved[wanted[key]] = url
    return resolved


def get_categories(page: Page) -> dict[str, str]:
    """Resolve category name -> URL, preferring the site's own categories
    API (https://sportoutlet.no/api/v1/categories) - the authoritative
    name-to-URL mapping, which matters because this site's slug text does
    not reliably reflect a page's content.

    DOM fallbacks if the API is unavailable or incomplete:
    1. anchors whose visible text is a category name (also after opening
       the Kategori filter and the Meny drawer);
    2. clicking each category name and capturing the navigation URL;
    3. probing candidate URLs and letting each page identify itself by
       its title / breadcrumb (never by slug or <h1>).
    """
    wanted = {_norm(name): name for name in CATEGORY_NAMES}
    resolved: dict[str, str] = _categories_from_api(page, wanted)
    if len(resolved) == len(wanted):
        return resolved

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
            else:
                # The click may only have expanded a submenu; links to the
                # category page might have appeared inside it.
                _merge_matching_links(page, {key: name}, resolved)
        except Exception:
            continue

    # Probe candidate URLs and let each page IDENTIFY itself. Slugs on
    # this site are scrambled relative to their content (verified live:
    # /kj%C3%A6ledyr titles itself "Alle produkter i Klær" and serves the
    # Klær category while its <h1> echoes the slug), so a slug or an <h1>
    # must never be trusted as the category identity - only the title
    # pattern / breadcrumb self-link says what a page really serves.
    candidates = [
        HOME_URL + urllib.parse.quote(_norm(name).replace(" ", "-"))
        for name in CATEGORY_NAMES
    ]
    if len(resolved) < len(wanted):
        candidates += _sitemap_candidates(page)
    probed: set[str] = set()
    for url in candidates:
        if len(resolved) == len(wanted):
            break
        if url in probed:
            continue
        probed.add(url)
        identified = _identify_category_page(page, url)
        if identified is None:
            continue
        key = _norm(identified)
        if key in wanted and wanted[key] not in resolved:
            resolved[wanted[key]] = url

    if not resolved:
        raise ScrapeError(
            f"could not resolve any category links on {START_URL} or {HOME_URL}"
        )
    return resolved


# "Alle produkter i Klær - Klær | Sport Outlet" -> "Klær"
_CATEGORY_TITLE_RE = re.compile(r"Alle produkter i (.+?)\s+[-–]")


def _identify_category_page(page: Page, url: str) -> str | None:
    """Load `url` and return the category name the page says it serves,
    or None if it isn't a working category page. Identity comes from the
    <title> ("Alle produkter i <name> - ...") or, failing that, the
    breadcrumb's self-link; the <h1> is deliberately ignored because it
    echoes the URL slug even when the slug is wrong.
    """
    try:
        response = page.goto(url, wait_until="domcontentloaded")
        if response is not None and response.status >= 400:
            return None
        page.wait_for_selector(PRODUCT_IMAGE_SELECTOR, timeout=10_000)
    except Exception:
        return None
    match = _CATEGORY_TITLE_RE.search(page.title() or "")
    if match:
        return match.group(1).strip()
    try:
        self_links = page.eval_on_selector_all(
            "a",
            "els => els.filter(e => e.href === location.href)"
            ".map(e => e.innerText.trim()).filter(t => t)",
        )
        for text in self_links:
            if _norm(text) != "hjem":
                return text
    except Exception:
        pass
    return None


def _sitemap_candidates(page: Page) -> list[str]:
    """Single-path-segment URLs from sitemap.xml (following one level of
    sitemap-index nesting) - candidate category pages to probe."""
    seen_xml: list[str] = [HOME_URL + "sitemap.xml"]
    pages: list[str] = []
    index = 0
    while index < len(seen_xml) and index < 10:
        xml_url = seen_xml[index]
        index += 1
        try:
            page.goto(xml_url, wait_until="domcontentloaded")
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", page.content())
        except Exception:
            continue
        for loc in locs:
            if loc.endswith(".xml"):
                if loc not in seen_xml:
                    seen_xml.append(loc)
                continue
            path = urllib.parse.urlparse(loc).path.strip("/")
            if path and "/" not in path:
                pages.append(loc)
    return pages[:150]


def get_sku_count(page: Page, start_url: str = START_URL) -> int:
    return count_unique_elements_by_scroll(
        page,
        start_url=start_url,
        selector=PRODUCT_IMAGE_SELECTOR,
        attribute="src",
        key_pattern=ARTICLE_ID_PATTERN,
        # Tiles whose CDN image failed to load show /storage/no-image.png
        # (no article id in the src); key those on the alt text so they
        # still count. Slight undercount possible if two same-named
        # variants both lack images, but far better than dropping them.
        fallback_attribute="alt",
    )

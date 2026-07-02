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

Per-category pages (e.g. https://sportoutlet.no/kl%C3%A6r) exist as an
alternative if /campaign ever stops being the full catalog, but summing
them isn't needed while /campaign covers "Alle".
"""
from __future__ import annotations

from playwright.sync_api import Page

from ._common import count_unique_elements_by_scroll

START_URL = "https://sportoutlet.no/campaign"
PRODUCT_IMAGE_SELECTOR = 'img[alt^="Image of product:"]'
ARTICLE_ID_PATTERN = r"/articles/[^/]+/"


def get_sku_count(page: Page) -> int:
    return count_unique_elements_by_scroll(
        page,
        start_url=START_URL,
        selector=PRODUCT_IMAGE_SELECTOR,
        attribute="src",
        key_pattern=ARTICLE_ID_PATTERN,
    )

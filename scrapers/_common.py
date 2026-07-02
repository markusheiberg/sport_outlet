"""Shared helpers for SKU-count scrapers."""
from __future__ import annotations

import csv
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

from playwright.sync_api import Browser, Page, sync_playwright

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_CSV = DATA_DIR / "sku_counts.csv"
CSV_FIELDS = ["timestamp_utc", "site", "sku_count", "status", "note"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class SiteResult:
    site: str
    sku_count: Optional[int]
    status: str  # "ok" | "error"
    note: str = ""


@contextmanager
def browser_page() -> Iterator[Page]:
    """Launch a single headless browser page, closed automatically."""
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            yield page
        finally:
            browser.close()


def count_products_by_pagination(
    page: Page,
    start_url: str,
    product_link_pattern: str,
    next_page_url: Optional[Callable[[str, int], str]] = None,
    load_more_selector: Optional[str] = None,
    max_pages: int = 500,
    stall_limit: int = 2,
) -> int:
    """Generic SKU counter: collect unique product-detail links across a
    paginated catalog until no new products appear.

    Pass exactly one pagination strategy:
    - `next_page_url(base_url, page_number) -> url` for URL-param pagination
      (e.g. `?page=N`).
    - `load_more_selector` for a "Load more" / infinite-scroll button that
      gets clicked repeatedly.
    Pass neither to scan only `start_url` as a single page.
    """
    link_re = re.compile(product_link_pattern)
    seen: set[str] = set()

    def collect_from_current_page() -> None:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        for href in hrefs:
            if link_re.search(href):
                seen.add(href)

    if load_more_selector:
        page.goto(start_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        stalled = 0
        for _ in range(max_pages):
            before = len(seen)
            collect_from_current_page()
            button = page.query_selector(load_more_selector)
            if button is None or not button.is_visible():
                break
            button.click()
            page.wait_for_timeout(800)
            stalled = stalled + 1 if len(seen) == before else 0
            if stalled >= stall_limit:
                break
    elif next_page_url:
        stalled = 0
        for i in range(1, max_pages + 1):
            page.goto(next_page_url(start_url, i), wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            before = len(seen)
            collect_from_current_page()
            stalled = stalled + 1 if len(seen) == before else 0
            if stalled >= stall_limit:
                break
    else:
        page.goto(start_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        collect_from_current_page()

    return len(seen)


def write_result(result: SiteResult) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not RESULTS_CSV.exists()
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "site": result.site,
                "sku_count": result.sku_count if result.sku_count is not None else "",
                "status": result.status,
                "note": result.note,
            }
        )

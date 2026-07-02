"""Entry point: run every site scraper once, write results, print summary.

Usage: python main.py
No scheduler involved - run this whenever you want a fresh snapshot.
"""
from __future__ import annotations

from scrapers import SITES
from scrapers._common import SiteResult, browser_page, write_result


def run_site(name: str, scrape_fn) -> SiteResult:
    try:
        with browser_page() as page:
            count = scrape_fn(page)
        return SiteResult(site=name, sku_count=count, status="ok")
    except Exception as exc:  # isolate failures - one site must never stop the others
        return SiteResult(site=name, sku_count=None, status="error", note=str(exc)[:200])


def main() -> None:
    results = [run_site(name, fn) for name, fn in SITES]
    for result in results:
        write_result(result)

    print(f"{'Site':<15}{'SKUs':>10}  Status")
    print("-" * 50)
    for r in results:
        count_display = r.sku_count if r.sku_count is not None else "NULL"
        note = f" - {r.note}" if r.note else ""
        print(f"{r.site:<15}{count_display!s:>10}  {r.status}{note}")


if __name__ == "__main__":
    main()

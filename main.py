"""Entry point: run every site scraper once, write results, print summary.

Usage: python main.py
No scheduler involved - run this whenever you want a fresh snapshot.

For each site, records one "all" row (whole catalog). Sites whose scraper
module exports get_categories() additionally get one row per category.
Note that per-category counts can sum to more than the "all" count when a
product is listed in several categories.
"""
from __future__ import annotations

from scrapers import SITES
from scrapers._common import SiteResult, browser_page, write_result


def _err_note(exc: Exception) -> str:
    """Exception message flattened to one line, truncated for the CSV."""
    return " ".join(str(exc).split())[:200]


def run_site(name: str, module) -> list[SiteResult]:
    results: list[SiteResult] = []
    try:
        with browser_page() as page:
            try:
                count = module.get_sku_count(page)
                results.append(SiteResult(site=name, sku_count=count, status="ok"))
            except Exception as exc:
                results.append(
                    SiteResult(site=name, sku_count=None, status="error", note=_err_note(exc))
                )

            if hasattr(module, "get_categories"):
                try:
                    categories = module.get_categories(page)
                except Exception as exc:
                    categories = {}
                    results.append(
                        SiteResult(
                            site=name,
                            sku_count=None,
                            status="error",
                            note=f"category discovery failed: {_err_note(exc)}"[:200],
                            category="(categories)",
                        )
                    )
                # Categories the module knows about but couldn't resolve a
                # URL for must surface as error rows, not vanish silently.
                for missing in getattr(module, "CATEGORY_NAMES", []):
                    if missing not in categories:
                        results.append(
                            SiteResult(
                                site=name,
                                sku_count=None,
                                status="error",
                                note="no URL resolved for this category",
                                category=missing,
                            )
                        )
                for cat_name, cat_url in categories.items():
                    try:
                        count = module.get_sku_count(page, cat_url)
                        results.append(
                            SiteResult(site=name, sku_count=count, status="ok", category=cat_name)
                        )
                    except Exception as exc:
                        results.append(
                            SiteResult(
                                site=name,
                                sku_count=None,
                                status="error",
                                note=_err_note(exc),
                                category=cat_name,
                            )
                        )
    except Exception as exc:  # isolate failures - one site must never stop the others
        results.append(
            SiteResult(site=name, sku_count=None, status="error", note=_err_note(exc))
        )
    return results


def main() -> None:
    results: list[SiteResult] = []
    for name, module in SITES:
        results.extend(run_site(name, module))
    for result in results:
        write_result(result)

    print(f"{'Site':<15}{'Category':<22}{'SKUs':>8}  Status")
    print("-" * 65)
    for r in results:
        count_display = r.sku_count if r.sku_count is not None else "NULL"
        note = f" - {r.note}" if r.note else ""
        print(f"{r.site:<15}{r.category:<22}{count_display!s:>8}  {r.status}{note}")


if __name__ == "__main__":
    main()

# CLAUDE.md — Nordic Sport Retail SKU Tracker

## What this does
Counts the number of SKUs (products) currently listed on Norwegian sport
retail websites (Sport Outlet, Anton Sport, Intersport, Sport1). This is an
on-demand snapshot tool, not a scheduled pipeline — you run it whenever you
want a fresh count.

## Architecture
Scrapers → local CSV.
- `scrapers/` — one module per site; `_common.py` holds shared helpers
  (headless browser launch, generic pagination-based SKU counter, CSV
  writer).
- `main.py` — entry point; runs every scraper once, appends one row per
  site to `data/sku_counts.csv`, and prints a summary table to the
  terminal.
- No scheduler, no cloud deployment, no database. Run `python main.py`
  by hand whenever you want a new snapshot; re-running over time builds
  up a simple trend in the CSV.

## How it runs
- A headless browser (Playwright) loads each site's product catalog and
  counts *unique product-detail-page links*, paginating through the
  catalog until no new products are found. This avoids relying on an
  "X products found" label, since not all sites show one.
- Each site has its own scraper module exporting `get_sku_count(page)`.
- Results are appended to `data/sku_counts.csv` — one timestamped row per
  site per run.

## Rules for Claude
- One site failing must never stop the others — `main.py` wraps each
  scraper call in try/except and continues to the next site.
- A failed read is stored as NULL (empty `sku_count`, `status=error`),
  never a guessed or zero value.
- Timestamps are UTC, ISO-8601.
- Don't commit secrets or credentials; ask before deploying anywhere.
- Never guess a site's pagination or selector logic. Verify against the
  live DOM (or user-provided page details) before writing scraper logic.
  A `NotImplementedError` stub is preferable to a plausible-looking but
  wrong count.

## Sites (site keys, immutable)
- `sportoutlet` — sportoutlet.no
- `antonsport` — antonsport.no
- `intersport` — intersport.no
- `sport1` — sport1.no

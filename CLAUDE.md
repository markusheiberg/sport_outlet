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
  terminal. Counts run in a thread pool (`--workers`, default 4); each
  worker drives its own headless browser because Playwright's sync API
  must not be shared across threads.
- No scheduler, no cloud deployment, no database. Run `python main.py`
  by hand whenever you want a new snapshot; re-running over time builds
  up a simple trend in the CSV.

## How it runs
- Preferred: read counts from a site's own catalog API when one exists.
  `sportoutlet` uses https://sportoutlet.no/api/v1/categories, whose
  per-main-group `articlesCount` is authoritative — the rendered catalog
  stops loading around ~1700 tiles regardless of scrolling, so DOM
  counting silently undercounts large categories there. Its `all` row is
  the sum over main groups (a product in two groups counts twice).
- Otherwise: a headless browser (Playwright) loads the site's product
  catalog and counts *unique product tiles/links*, paginating or
  scrolling until no new products appear. Beware rendering caps like the
  one above — validate a big category against the site's own numbers
  before trusting scroll-based counts.
- Each site has its own scraper module exporting `get_sku_count(page)`.
  A module may also export `get_categories(page) -> {name: url}`; when it
  does, `main.py` records one extra row per category alongside the
  whole-catalog `all` row. Category URLs are resolved from the live DOM by
  visible link text — never from guessed slugs.
- Results are appended to `data/sku_counts.csv` — one timestamped row per
  site (and per category, where supported) per run. The `category` column
  is `all` for whole-catalog counts. Per-category counts may sum to more
  than `all` because one product can be listed in several categories.

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
- `xxl` — xxl.no
- `antonsport` — antonsport.no
- `intersport` — intersport.no
- `sport1` — sport1.no

from . import antonsport, intersport, sport1, sportoutlet

# Each module exports get_sku_count(page) for the whole catalog, and may
# optionally export get_categories(page) -> {name: url} plus a
# get_sku_count(page, start_url) overload for per-category counts.
SITES = [
    ("sportoutlet", sportoutlet),
    ("antonsport", antonsport),
    ("intersport", intersport),
    ("sport1", sport1),
]

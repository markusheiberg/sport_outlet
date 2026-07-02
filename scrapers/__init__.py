from . import antonsport, intersport, sport1, sportoutlet

SITES = [
    ("sportoutlet", sportoutlet.get_sku_count),
    ("antonsport", antonsport.get_sku_count),
    ("intersport", intersport.get_sku_count),
    ("sport1", sport1.get_sku_count),
]

"""Diagnose why a scraper finds no product tiles on a page.

Usage: python debug_page.py [url]   (default: the Sport Outlet catalog)

Loads the URL in the same headless browser the scrapers use, then prints
what actually rendered: final URL, title, image/link tallies, sample img
alt/src values, and candidate consent buttons. Saves a full-page
screenshot and the rendered HTML next to this script for inspection.
"""
from __future__ import annotations

import sys

from scrapers._common import browser_page, dismiss_cookie_banner

DEFAULT_URL = "https://sportoutlet.no/campaign"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    with browser_page() as page:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        print(f"requested url : {url}")
        print(f"final url     : {page.url}")
        print(f"title         : {page.title()}")

        buttons = page.eval_on_selector_all(
            "button", "els => els.map(e => e.innerText.trim()).filter(t => t).slice(0, 20)"
        )
        print(f"button texts  : {buttons}")

        dismiss_cookie_banner(page)
        page.wait_for_timeout(3000)

        imgs = page.eval_on_selector_all(
            "img", "els => els.map(e => ({alt: e.getAttribute('alt'), src: e.getAttribute('src')}))"
        )
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        print(f"img count     : {len(imgs)}")
        print(f"link count    : {len(links)}")
        print("first 15 imgs :")
        for img in imgs[:15]:
            print(f"  alt={img['alt']!r} src={str(img['src'])[:100]!r}")
        product_imgs = [i for i in imgs if (i["alt"] or "").startswith("Image of product:")]
        print(f"imgs matching 'Image of product:' prefix: {len(product_imgs)}")
        print("first 15 links:")
        for href in links[:15]:
            print(f"  {href}")

        page.screenshot(path="debug_screenshot.png", full_page=False)
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("saved debug_screenshot.png and debug_page.html")


if __name__ == "__main__":
    main()

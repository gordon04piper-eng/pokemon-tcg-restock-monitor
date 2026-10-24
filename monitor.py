"""
Pokemon Card Multi-Site Monitor
---------------------------------
Monitors multiple NZ retailers for Pokemon card restocks.
Sends a Discord alert when new products are found.

Setup:
    1. pip install -r requirements.txt
    2. Copy .env.example to .env and put your Discord webhook URL in it
    3. Launch Chrome with remote debugging (Windows example):
       "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\\ChromeDebug
    4. Run: python monitor.py
"""

import asyncio
import logging
import os
import random
import requests
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; you can also set the variable in your environment

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

# Read from the environment (.env file) so the webhook is never stored in the code
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# How often to check each site (seconds)
REFRESH_INTERVAL = 60

# Sites to monitor. Set enabled: False to skip any site
SITES = [
    {
        "name": "Mighty Ape",
        "url": "https://www.mightyape.co.nz/mn/c/pokemon-trading-card-game/?deals_from=mightyape",
        "title_selector": "h6.font-title-list",
        "title_method": "inner_text",
        "link_selector": "a",
        "link_parent": True,
        "base_url": "https://www.mightyape.co.nz",
        "enabled": True,
        "track_stock": True,
    },
    {
        "name": "JB Hi-Fi",
        "url": "https://www.jbhifi.co.nz/search?query=pokemon%20tcg",
        "title_selector": "div[data-testid='product-card-title']",
        "title_method": "inner_text",
        "link_selector": "a[data-testid='product-card-content-link']",
        "link_parent": False,
        "base_url": "https://www.jbhifi.co.nz",
        "enabled": True,
    },
]

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("monitor_log.txt"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  DISCORD
# ─────────────────────────────────────────────

def send_discord_alert(site_name: str, title: str, price: str, url: str):
    if not DISCORD_WEBHOOK_URL:
        log.warning("  DISCORD_WEBHOOK_URL is not set, skipping alert.")
        return

    message = {
        "embeds": [
            {
                "title": f"🚨 New Pokemon Card — {site_name}!",
                "color": 0xFF0000,
                "fields": [
                    {"name": "Product", "value": title, "inline": False},
                    {"name": "Price", "value": price if price else "Unknown", "inline": True},
                    {"name": "Link", "value": url if url else "", "inline": False},
                ],
                "footer": {"text": f"Detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
            }
        ],
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message)
        if response.status_code == 204:
            log.info("  ✓ Discord alert sent!")
        else:
            log.warning(f"  Discord alert failed — {response.status_code}: {response.text}")
    except Exception as e:
        log.error(f"  Discord error: {e}")


def send_blocked_alert(site_name: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": f"⚠️ **{site_name}** monitor blocked or returning no products — may need restart!"
        })
    except Exception:
        pass


# ─────────────────────────────────────────────
#  SCRAPER
# ─────────────────────────────────────────────

async def scrape_site(page, site: dict) -> list:
    """Visit a site and return list of {title, url} dicts."""
    try:
        await page.goto(site["url"], wait_until="domcontentloaded", timeout=20000)
    except PlaywrightTimeout:
        log.warning(f"  [{site['name']}] Page load timed out.")
        return []

    await asyncio.sleep(random.uniform(2.0, 3.5))

    # Check for Cloudflare block
    content = await page.content()
    if "Access is temporarily restricted" in content or "unusual activity" in content:
        log.warning(f"  [{site['name']}] Cloudflare block detected.")
        send_blocked_alert(site["name"])
        return []

    # Scroll to trigger lazy loading
    await page.mouse.wheel(0, random.randint(300, 600))
    await asyncio.sleep(1.0)

    products = []
    try:
        title_els = await page.query_selector_all(site["title_selector"])

        for title_el in title_els:
            try:
                # Get title text
                if site["title_method"] == "inner_text":
                    title = (await title_el.inner_text()).strip()
                else:
                    title = (await title_el.get_attribute("alt") or "").strip()

                if not title:
                    continue

                # Get product URL
                url = None
                if site["link_parent"]:
                    link_el = await title_el.evaluate_handle("el => el.closest('a')")
                    href = await link_el.get_attribute("href") if link_el else None
                else:
                    # Find nearest sibling or parent link
                    siblings = await page.query_selector_all(site["link_selector"])
                    href = None
                    for s in siblings:
                        s_text = await s.inner_text() if site["title_method"] == "inner_text" else ""
                        if title.lower()[:20] in s_text.lower() or True:
                            href = await s.get_attribute("href")
                            if href:
                                break

                if href:
                    url = f"{site['base_url']}{href}" if href.startswith("/") else href

                # Get stock status for Mighty Ape
                stock = ""
                if site.get("track_stock"):
                    try:
                        container = await title_el.evaluate_handle("el => el.closest('a') ? el.closest('a').parentElement : el.parentElement")
                        stock_el = await container.query_selector("span.text-text-surface-in-stock, span.text-price-list-secondary")
                        stock = (await stock_el.inner_text()).strip() if stock_el else ""
                    except Exception:
                        pass

                products.append({"title": title, "url": url or site["url"], "price": "", "stock": stock})

            except Exception:
                continue

    except Exception as e:
        log.error(f"  [{site['name']}] Scrape error: {e}")

    return products


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

async def run():
    # Track what we've already alerted for per site
    alerted = {site["name"]: set() for site in SITES}
    stock_status = {}  # tracks {title: "In stock" / "Sold out"} for Mighty Ape

    async with async_playwright() as p:
        log.info("Connecting to Chrome...")
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            log.error(f"Could not connect to Chrome: {e}")
            log.error("Make sure you launched Chrome with --remote-debugging-port=9222")
            return

        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        enabled_sites = [s for s in SITES if s["enabled"]]
        log.info(f"Monitoring {len(enabled_sites)} sites:")
        for site in enabled_sites:
            log.info(f"  • {site['name']}")
        log.info(f"Refresh interval: {REFRESH_INTERVAL}s")
        log.info("-" * 50)

        first_run = True
        while True:
            for site in enabled_sites:
                log.info(f"Checking {site['name']}...")
                products = await scrape_site(page, site)

                if not products:
                    log.warning(f"  [{site['name']}] No products found.")
                else:
                    log.info(f"  [{site['name']}] Found {len(products)} products.")

                # Stock change detection for Mighty Ape
                if site.get("track_stock") and not first_run:
                    for product in products:
                        title = product["title"]
                        new_status = product.get("stock", "")
                        old_status = stock_status.get(title, "")
                        if old_status == "Sold out" and new_status == "In stock":
                            log.info(f"  RESTOCK: {title}")
                            send_discord_alert("Mighty Ape 🔄 RESTOCK", title, product["price"], product["url"])
                        stock_status[title] = new_status

                new_count = 0
                for product in products:
                    title = product["title"]
                    if title in alerted[site["name"]]:
                        continue

                    alerted[site["name"]].add(title)
                    if first_run:
                        continue

                    log.info(f"  NEW: {title}")
                    send_discord_alert(site["name"], title, product["price"], product["url"])
                    new_count += 1
                    await asyncio.sleep(0.5)  # Small delay between alerts

                if new_count == 0 and products:
                    log.info(f"  [{site['name']}] No new products since last check.")

                # Small delay between sites
                await asyncio.sleep(random.uniform(3, 6))

            first_run = False
            wait = REFRESH_INTERVAL + random.uniform(-10, 10)
            log.info(f"All sites checked. Next round in {wait:.0f}s...")
            await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(run())

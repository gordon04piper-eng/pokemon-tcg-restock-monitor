# Pokemon TCG Restock Monitor

A Python script that watches New Zealand retail sites (Mighty Ape and JB Hi-Fi) for Pokemon trading card restocks and sends an alert to a Discord channel when something new appears or comes back in stock.

## How it works

- Uses Playwright to connect to a Chrome window you launch with remote debugging, and loads each retailer's Pokemon TCG page on a timer.
- Reads the product titles and links from the page, and remembers what it has already seen.
- On Mighty Ape it also tracks stock status, so a sold out item that returns to "In stock" triggers a restock alert.
- Sends alerts through a Discord webhook, and posts a warning if a site blocks the monitor.

## Setup

1. Install the dependencies:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Copy `.env.example` to `.env` and put your Discord webhook URL in it.
3. Launch Chrome with remote debugging (Windows example):
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug
   ```
4. Run the monitor:
   ```
   python monitor.py
   ```

## Notes

- Built as a personal project. Sites can change their layout, so the selectors in `SITES` may need updating.
- Check each retailer's terms before running it, and keep the refresh interval reasonable.

Tech: Python, Playwright, asyncio, Requests, Discord webhooks

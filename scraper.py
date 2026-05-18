import asyncio
import json
import os
import traceback
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

def load_json(filepath, default_value):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_value

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

URLS = [
    "https://www.sma.de/produkte/solar-wechselrichter/sunny-boy-15-20-25",
    "https://www.sma.de/produkte/solar-wechselrichter/sunny-tripower-x-60"
]
DATEN_DATEI = "sma_daten.json"
HISTORY_DATEI = "history.json"

def extrahiere_links(html):
    soup = BeautifulSoup(html, 'html.parser')
    ergebnisse = {}

    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)

        if href.startswith('#'):
            continue

        # Check if it's a file download or firmware update or has 'download'
        if 'download' in href.lower() or 'firmware' in text.lower() or '.pdf' in href.lower() or '.zip' in href.lower() or 'zertifikat' in text.lower():
            if not text or text.lower() == 'download':
                # Try to find a better text by looking at parent rows or previous elements
                parent_td = a.find_parent('td')
                if parent_td:
                    prev_td = parent_td.find_previous_sibling('td')
                    if prev_td:
                        text = prev_td.get_text(strip=True)
                elif 'download' in href.lower():
                    # fallback to filename
                    text = href.split('/')[-1]

            if text and href:
                # normalize href
                if href.startswith('/'):
                    href = "https://www.sma.de" + href
                ergebnisse[href] = {
                    "Titel": text,
                    "Link": href
                }
    return ergebnisse

async def hole_daten():
    print(f"🚀 Starte Browser für SMA Überwachung...")

    alle_daten = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for url in URLS:
            print(f"   Lade Seite: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000) # Give it some time to render JS
                html = await page.content()
                daten = extrahiere_links(html)
                print(f"   => {len(daten)} Downloads/Links auf {url} gefunden.")
                alle_daten.update(daten)
            except Exception as e:
                print(f"⚠️ Fehler beim Abrufen der Seite {url}: {e}")

        await browser.close()

    return alle_daten

async def main():
    neue_daten = await hole_daten()
    if not neue_daten:
        print("❌ Keine Daten gefunden.")
        return

    alte_daten = load_json(DATEN_DATEI, {})

    neue_funde = []
    anderungen = []

    for url, daten in neue_daten.items():
        if url not in alte_daten:
            neue_funde.append({"url": url, "bezeichnung": daten['Titel'], "typ": "NEU"})
        elif alte_daten[url] != daten:
            anderungen.append({"url": url, "bezeichnung": daten['Titel'], "typ": "UPDATE"})

    # Check for removed items? For now we just care about new and updated, just like hw-monitor

    if neue_funde or anderungen:
        print(f"\n✨ {len(neue_funde)} neue und {len(anderungen)} geänderte Dokumente gefunden!")
    else:
        print("\n✅ Alles unverändert.")

    history = load_json(HISTORY_DATEI, [])

    eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "funde": neue_funde + anderungen
    }

    history.insert(0, eintrag)
    history = history[:30]

    save_json(HISTORY_DATEI, history)
    print(f"💾 Historie in {HISTORY_DATEI} gespeichert.")

    save_json(DATEN_DATEI, neue_daten)
    print(f"💾 Daten in {DATEN_DATEI} aktualisiert.")

if __name__ == "__main__":
    asyncio.run(main())

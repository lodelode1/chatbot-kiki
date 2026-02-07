"""
Haal de ontbrekende nieuwsbrieven op van kiesraad.email-provider.eu.
Eenmalig script — voegt ze toe aan metadata en slaat HTML op.
"""

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_HTML_DIR = DATA_DIR / "raw" / "html"
METADATA_FILE = DATA_DIR / "metadata.json"

HEADERS = {
    "User-Agent": "VerkiezingenBot/1.0 (educatief project)"
}

NIEUWSBRIEVEN = [
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/gb39f0v790?lp%2Dt=1768825519",
        "title": "Nieuwsbrief Verkiezingen januari 2026 Nr. 10",
        "filename": "nieuwsbrief_nr10_jan2026.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/bulx3ysnhr",
        "title": "Nieuwsbrief Verkiezingen december 2025 Nr. 9",
        "filename": "nieuwsbrief_nr09_dec2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/buue7r24ff",
        "title": "Nieuwsbrief Verkiezingen november 2025 Nr. 8",
        "filename": "nieuwsbrief_nr08_nov2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/vvj80lkg3c",
        "title": "Nieuwsbrief Verkiezingen november 2025 Nr. 7",
        "filename": "nieuwsbrief_nr07_nov2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/gemh01cnqt?lp%2Dt=1759404513",
        "title": "Nieuwsbrief Verkiezingen oktober 2025 Nr. 5",
        "filename": "nieuwsbrief_nr05_okt2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/rs1hc7o99d",
        "title": "Nieuwsbrief Verkiezingen september 2025 Nr. 4",
        "filename": "nieuwsbrief_nr04_sep2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/na8afa8egg?lp%2Dt=1756395032",
        "title": "Nieuwsbrief Verkiezingen augustus 2025 Nr. 3",
        "filename": "nieuwsbrief_nr03_aug2025.html",
    },
    {
        "url": "https://kiesraad.email-provider.eu/web/smlggvqpgq/oss4qtb2k1?lp%2Dt=1752140961",
        "title": "Nieuwsbrief Verkiezingen juli 2025 Nr. 2",
        "filename": "nieuwsbrief_nr02_jul2025.html",
    },
]


def run():
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    # Laad bestaande metadata
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Check welke al bestaan
    existing_urls = {item["url"] for item in metadata}

    added = 0
    for nb in NIEUWSBRIEVEN:
        if nb["url"] in existing_urls:
            print(f"  Al aanwezig: {nb['title']}")
            continue

        print(f"  Ophalen: {nb['title']}...")
        try:
            time.sleep(1)
            response = requests.get(nb["url"], headers=HEADERS, timeout=30)
            response.raise_for_status()

            # Sla HTML op
            filepath = RAW_HTML_DIR / nb["filename"]
            filepath.write_text(response.text, encoding="utf-8")

            # Voeg toe aan metadata
            metadata.append({
                "url": nb["url"],
                "title": nb["title"],
                "type": "nieuwsbrief",
                "html_file": str(filepath),
                "sectie": "nieuwsbrieven",
            })
            added += 1
            print(f"    Opgeslagen: {nb['filename']}")

        except requests.RequestException as e:
            print(f"    FOUT: {e}")

    # Sla metadata op
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"\n{added} nieuwsbrieven toegevoegd.")


if __name__ == "__main__":
    run()

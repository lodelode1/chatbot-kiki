"""
Scraper voor de Kiesraad Toolkit Verkiezingen GR26.

Scraped ALLEEN documenten van de opgegeven hoofdpagina en diens subpagina's.
Gaat NIET recursief de hele kiesraad.nl of rijksoverheid.nl af.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://www.kiesraad.nl/verkiezingen/gemeenteraden/documenten-gemeenteraadsverkiezing-2026"
ALLOWED_DOMAINS = ["www.kiesraad.nl", "www.rijksoverheid.nl"]
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_HTML_DIR = DATA_DIR / "raw" / "html"
RAW_PDF_DIR = DATA_DIR / "raw" / "pdf"
METADATA_FILE = DATA_DIR / "metadata.json"

# Polite scraping
REQUEST_DELAY = 1.0  # seconden tussen requests
HEADERS = {
    "User-Agent": "VerkiezingenBot/1.0 (educatief project; scrapet alleen toolkit-documenten)"
}


def get_soup(url: str) -> BeautifulSoup | None:
    """Haal een pagina op en geef BeautifulSoup object terug."""
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"  FOUT bij ophalen {url}: {e}")
        return None


def safe_filename(url: str, extension: str = "") -> str:
    """Maak een veilige bestandsnaam van een URL. Beperkt tot 150 tekens voor Windows."""
    parsed = urlparse(url)
    # Gebruik alleen het laatste deel van het pad
    path_parts = parsed.path.strip("/").split("/")
    name = path_parts[-1] if path_parts else "index"
    name = re.sub(r"[^\w\-.]", "_", name)
    if not name:
        name = "index"
    # Beperk lengte, voeg hash toe bij afkapping voor uniciteit
    max_len = 120
    if extension and not name.endswith(extension):
        name += extension
    if len(name) > max_len:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        name = name[:max_len - 9] + "_" + url_hash + extension
    return name


def get_subpage_urls(soup: BeautifulSoup) -> list[str]:
    """Vind alle subpagina-links op de hoofdpagina."""
    subpages = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(BASE_URL, href)
        # Alleen subpagina's van de toolkit
        if full_url.startswith(BASE_URL + "/") and full_url != BASE_URL:
            if full_url not in subpages:
                subpages.append(full_url)
    return subpages


def get_document_links(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Vind alle document-links op een subpagina."""
    documents = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(page_url, href)
        parsed = urlparse(full_url)

        # Alleen links naar toegestane domeinen
        if parsed.hostname not in ALLOWED_DOMAINS:
            continue

        # Sla navigatie-links en de toolkit-pagina's zelf over
        if full_url.startswith(BASE_URL):
            continue

        # Voorkom duplicaten
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = link.get_text(strip=True)
        if not title:
            continue

        documents.append({
            "url": full_url,
            "title": title,
            "found_on": page_url,
        })

    return documents


def download_pdfs_from_page(doc_url: str, soup: BeautifulSoup | None = None) -> list[str]:
    """
    Bezoek een documentpagina en download ALLE PDF-bestanden.
    Retourneert een lijst met paden naar gedownloade bestanden.
    """
    if soup is None:
        soup = get_soup(doc_url)
    if not soup:
        return []

    # Zoek naar directe PDF-links op de pagina
    pdf_links = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.lower().endswith(".pdf"):
            full_url = urljoin(doc_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)

    if not pdf_links:
        return []

    # Download alle PDF's
    downloaded = []
    for pdf_url in pdf_links:
        # Sla over als al gedownload
        filename = safe_filename(pdf_url, ".pdf")
        filepath = RAW_PDF_DIR / filename
        if filepath.exists():
            downloaded.append(str(filepath))
            continue

        try:
            time.sleep(REQUEST_DELAY)
            response = requests.get(pdf_url, headers=HEADERS, timeout=60)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type or pdf_url.lower().endswith(".pdf"):
                filepath.write_bytes(response.content)
                downloaded.append(str(filepath))
        except requests.RequestException as e:
            print(f"  FOUT bij downloaden PDF {pdf_url}: {e}")

    return downloaded


def save_html(url: str, soup: BeautifulSoup) -> str:
    """Sla de HTML-inhoud op als bestand."""
    filename = safe_filename(url, ".html")
    filepath = RAW_HTML_DIR / filename
    filepath.write_text(str(soup), encoding="utf-8")
    return str(filepath)


def run():
    """Voer de scraper uit."""
    # Maak mappen aan
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)

    metadata = []

    # Stap 1: Haal de hoofdpagina op
    print(f"Ophalen hoofdpagina: {BASE_URL}")
    main_soup = get_soup(BASE_URL)
    if not main_soup:
        print("FOUT: Kan hoofdpagina niet ophalen. Afgebroken.")
        return

    html_path = save_html(BASE_URL, main_soup)
    metadata.append({
        "url": BASE_URL,
        "title": "GR26 Toolkit Verkiezingen - Hoofdpagina",
        "type": "hoofdpagina",
        "html_file": html_path,
        "sectie": "overzicht",
    })

    # Stap 2: Vind alle subpagina's
    subpage_urls = get_subpage_urls(main_soup)
    print(f"\nGevonden subpagina's: {len(subpage_urls)}")
    for url in subpage_urls:
        print(f"  - {url}")

    # Stap 3: Verwerk elke subpagina
    all_documents = []
    for subpage_url in tqdm(subpage_urls, desc="Subpagina's verwerken"):
        soup = get_soup(subpage_url)
        if not soup:
            continue

        # Bepaal sectienaam
        sectie = subpage_url.split("/")[-1].replace("gr26-", "").replace("-", " ")

        # Sla HTML op
        html_path = save_html(subpage_url, soup)

        # Haal de paginatitel op
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else sectie

        metadata.append({
            "url": subpage_url,
            "title": title,
            "type": "subpagina",
            "html_file": html_path,
            "sectie": sectie,
        })

        # Verzamel document-links
        docs = get_document_links(soup, subpage_url)
        all_documents.extend(docs)

    # Verwijder duplicaten op URL
    seen = set()
    unique_docs = []
    for doc in all_documents:
        if doc["url"] not in seen:
            seen.add(doc["url"])
            unique_docs.append(doc)

    print(f"\nGevonden unieke document-links: {len(unique_docs)}")

    # Stap 4: Bezoek elke documentpagina en download PDF's
    pdf_count = 0
    for doc in tqdm(unique_docs, desc="Documenten verwerken"):
        # Bezoek de documentpagina
        soup = get_soup(doc["url"])
        if soup:
            html_path = save_html(doc["url"], soup)
            doc["html_file"] = html_path

            # Probeer de paginatekst te bewaren (nuttig voor de parser)
            main_content = soup.find("main") or soup.find("article") or soup
            doc["has_page_content"] = len(main_content.get_text(strip=True)) > 100

        # Download alle PDF's van de pagina
        pdf_paths = download_pdfs_from_page(doc["url"], soup)
        if pdf_paths:
            doc["pdf_files"] = pdf_paths
            doc["pdf_file"] = pdf_paths[0]  # Eerste voor backwards compatibility
            doc["type"] = "pdf"
            pdf_count += len(pdf_paths)
        else:
            doc["type"] = "webpagina"

        # Bepaal sectie op basis van waar het document gevonden is
        found_page = doc["found_on"].split("/")[-1]
        doc["sectie"] = found_page.replace("gr26-", "").replace("-", " ")

        metadata.append(doc)

    # Stap 5: Sla metadata op
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Samenvatting
    print("\n" + "=" * 50)
    print("SCRAPER VOLTOOID")
    print("=" * 50)
    print(f"Subpagina's verwerkt:  {len(subpage_urls)}")
    print(f"Document-links gevonden: {len(unique_docs)}")
    print(f"PDF's gedownload:      {pdf_count}")
    print(f"Metadata opgeslagen:   {METADATA_FILE}")
    print(f"HTML-bestanden:        {RAW_HTML_DIR}")
    print(f"PDF-bestanden:         {RAW_PDF_DIR}")


if __name__ == "__main__":
    run()

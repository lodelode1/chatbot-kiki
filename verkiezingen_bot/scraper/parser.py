"""
Parser: zet ruwe HTML- en PDF-bestanden om naar gestructureerde tekst.

Elke passage bevat: tekst, bron-url, sectie, titel.
Output: data/clean/passages.json
"""

import json
import re
from pathlib import Path

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from tqdm import tqdm

DATA_DIR = Path(__file__).parent.parent / "data"
METADATA_FILE = DATA_DIR / "metadata.json"
CLEAN_DIR = DATA_DIR / "clean"
OUTPUT_FILE = CLEAN_DIR / "passages.json"

# Patronen voor footer-tekst die van passages gestript moet worden
FOOTER_MARKERS = [
    "Meer informatie\nMeer informatie over het organiseren van verkiezingen",
    "Meer informatie\nHeb je nog vragen over de organisatie van verkiezingen",
    "Meer informatie\nHeb je vragen over de organisatie van verkiezingen",
    "Meer informatie Meer informatie over het organiseren van verkiezingen",
    "Meer informatie Heb je nog vragen over de organisatie van verkiezingen",
    "Meer informatie Heb je vragen over de organisatie van verkiezingen",
    "Wil je de Nieuwsbrief Verkiezingen zelf ook ontvangen?",
    "Deze e-mail is verstuurd aan",
    "Vragen over de organisatie van verkiezingen?Neem contact op met het",
    "Vragen over de organisatie van verkiezingen?\nNeem contact op met het",
]


def clean_text(text: str) -> str:
    """Verwijder overbodige witruimte en lege regels."""
    # Verwijder meerdere spaties
    text = re.sub(r"[ \t]+", " ", text)
    # Verwijder meer dan 2 opeenvolgende lege regels
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip elke regel
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


def strip_footer(text: str) -> str:
    """Verwijder bekende boilerplate footers van het eind van een passage."""
    for marker in FOOTER_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()
    return text


def is_boilerplate(heading: str, text: str) -> bool:
    """Controleer of een passage puur boilerplate is en verwijderd moet worden."""
    # "Deel deze pagina" social media knoppen
    if heading == "Deel deze pagina" or text.startswith("Deel deze pagina"):
        return True

    # Te kort om nuttig te zijn
    if len(text) < 50:
        return True

    # PDF-artefact: overwegend alleen nummers (kandidatenlijst rijnummers)
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) > 5:
        digit_lines = sum(1 for l in lines if l.strip().isdigit())
        if digit_lines / len(lines) > 0.7:
            return True

    # Pure footer (geen inhoud voor de footer)
    for marker in FOOTER_MARKERS:
        if text.startswith(marker) or text.startswith("Meer informatie\n" + marker.split("\n", 1)[-1] if "\n" in marker else marker):
            return True

    return False


def parse_html(html_path: str) -> list[dict]:
    """
    Parse een HTML-bestand naar gestructureerde tekstpassages.
    Behoudt headings als structuurelementen.
    """
    path = Path(html_path)
    if not path.exists():
        return []

    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Verwijder scripts, styles en navigatie
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Zoek de hoofd-content
    main = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup

    passages = []
    current_heading = ""
    current_text_parts = []

    for element in main.descendants:
        if element.name in ("h1", "h2", "h3", "h4"):
            # Sla vorige sectie op als er tekst is
            if current_text_parts:
                text = clean_text("\n".join(current_text_parts))
                if len(text) > 30:  # Minimale lengte
                    passages.append({
                        "heading": current_heading,
                        "text": text,
                    })
                current_text_parts = []
            current_heading = element.get_text(strip=True)

        elif element.name in ("p", "li", "td", "th", "dt", "dd", "blockquote"):
            text = element.get_text(strip=True)
            if text and len(text) > 5:
                current_text_parts.append(text)

    # Laatste sectie opslaan
    if current_text_parts:
        text = clean_text("\n".join(current_text_parts))
        if len(text) > 30:
            passages.append({
                "heading": current_heading,
                "text": text,
            })

    return passages


def parse_pdf(pdf_path: str) -> list[dict]:
    """
    Parse een PDF-bestand naar tekstpassages per pagina.
    """
    path = Path(pdf_path)
    if not path.exists():
        return []

    passages = []
    try:
        doc = fitz.open(str(path))
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            text = clean_text(text)
            if len(text) > 30:
                passages.append({
                    "heading": f"Pagina {page_num}",
                    "text": text,
                })
        doc.close()
    except Exception as e:
        print(f"  FOUT bij PDF parsing {pdf_path}: {e}")

    return passages


def run():
    """Voer de parser uit op alle gescrapete bestanden."""
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # Laad metadata
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    all_passages = []
    html_count = 0
    pdf_count = 0
    skipped = 0

    for item in tqdm(metadata, desc="Bestanden parsen"):
        url = item.get("url", "")
        title = item.get("title", "")
        sectie = item.get("sectie", "")
        item_type = item.get("type", "")

        passages = []

        # Parse alle PDF's als die er zijn
        pdf_files = item.get("pdf_files", [])
        if not pdf_files:
            # Backwards compatibility: enkel pdf_file veld
            single = item.get("pdf_file")
            if single:
                pdf_files = [single]
        for pdf_file in pdf_files:
            if Path(pdf_file).exists():
                pdf_passages = parse_pdf(pdf_file)
                # Voeg bestandsnaam toe zodat versies te onderscheiden zijn
                pdf_name = Path(pdf_file).stem
                for p in pdf_passages:
                    p["bron_bestand"] = pdf_name
                passages.extend(pdf_passages)
                pdf_count += 1

        # Parse HTML: altijd als primaire bron bij (sub)pagina's,
        # en als aanvullende toelichting bij PDF-documenten
        html_file = item.get("html_file")
        if html_file and Path(html_file).exists():
            html_passages = parse_html(html_file)
            if html_passages:
                if item_type in ("subpagina", "hoofdpagina"):
                    # Bij subpagina's: gebruik HTML als primaire bron
                    passages = html_passages
                elif not passages:
                    # Bij documenten zonder PDF: gebruik HTML
                    passages = html_passages
                else:
                    # Bij documenten met PDF: voeg HTML-toelichting toe
                    # (bevat vaak context over wijzigingen, etc.)
                    passages.extend(html_passages)
                html_count += 1

        if not passages:
            skipped += 1
            continue

        # Voeg metadata toe aan elke passage
        for passage in passages:
            passage["bron_url"] = url
            passage["titel"] = title
            passage["sectie"] = sectie
            passage["type"] = item_type

        all_passages.extend(passages)

    # --- Opschoonfase ---
    raw_count = len(all_passages)

    # 1. Strip footers van alle passages
    for passage in all_passages:
        passage["text"] = strip_footer(passage["text"])

    # 2. Verwijder boilerplate passages
    all_passages = [
        p for p in all_passages
        if not is_boilerplate(p.get("heading", ""), p["text"])
    ]
    boilerplate_removed = raw_count - len(all_passages)

    # 3. Dedupliceer op basis van tekst
    seen_texts = set()
    unique_passages = []
    for p in all_passages:
        # Normaliseer voor vergelijking (strip witruimte)
        norm = re.sub(r"\s+", " ", p["text"]).strip()
        if norm not in seen_texts:
            seen_texts.add(norm)
            unique_passages.append(p)
    duplicates_removed = len(all_passages) - len(unique_passages)
    all_passages = unique_passages

    # Geef elke passage een uniek ID
    for i, passage in enumerate(all_passages):
        passage["id"] = i

    # Sla op
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_passages, f, ensure_ascii=False, indent=2)

    # Samenvatting
    print("\n" + "=" * 50)
    print("PARSER VOLTOOID")
    print("=" * 50)
    print(f"HTML-bestanden verwerkt: {html_count}")
    print(f"PDF-bestanden verwerkt:  {pdf_count}")
    print(f"Overgeslagen:           {skipped}")
    print(f"Passages (ruw):         {raw_count}")
    print(f"Boilerplate verwijderd: {boilerplate_removed}")
    print(f"Duplicaten verwijderd:  {duplicates_removed}")
    print(f"Passages (schoon):      {len(all_passages)}")
    print(f"Output:                 {OUTPUT_FILE}")

    # Steekproef
    print("\n--- Steekproef (eerste 3 passages) ---")
    for p in all_passages[:3]:
        print(f"\n[{p['type']}] {p['titel']}")
        print(f"  Sectie: {p['sectie']}")
        print(f"  Heading: {p['heading']}")
        print(f"  Tekst: {p['text'][:150]}...")


if __name__ == "__main__":
    run()

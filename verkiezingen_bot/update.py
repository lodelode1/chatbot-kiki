"""
Incrementele update: detecteer nieuwe documenten op de toolkit en voeg ze toe.

Scrapet de toolkit-pagina's opnieuw, vergelijkt met bestaande metadata,
en verwerkt alleen nieuwe bestanden (download → parse → index).

Gebruik:
    python -m verkiezingen_bot.update
"""

import json
import pickle
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from verkiezingen_bot.scraper.scraper import (
    BASE_URL,
    RAW_HTML_DIR,
    RAW_PDF_DIR,
    METADATA_FILE,
    get_soup,
    get_subpage_urls,
    get_document_links,
    download_pdfs_from_page,
    save_html,
)
from verkiezingen_bot.scraper.parser import (
    parse_html,
    parse_pdf,
    strip_footer,
    is_boilerplate,
    clean_text,
    OUTPUT_FILE as PASSAGES_FILE,
    CLEAN_DIR,
)
from verkiezingen_bot.app.indexer import (
    split_into_chunks,
    FAISS_INDEX_FILE,
    CHUNKS_FILE,
    MODEL_NAME,
    INDEX_DIR,
)


def load_existing_metadata() -> list[dict]:
    """Laad bestaande metadata, of lege lijst als bestand niet bestaat."""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_existing_passages() -> list[dict]:
    """Laad bestaande passages."""
    if PASSAGES_FILE.exists():
        with open(PASSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def discover_current_urls() -> tuple[list[dict], list[dict]]:
    """
    Scrape de toolkit en retourneer alle huidige subpagina's en document-links.

    Returns:
        (subpagina_items, document_items)
    """
    print("=== Stap 1: Toolkit scannen op nieuwe documenten ===\n")

    # Haal hoofdpagina op
    print(f"Ophalen hoofdpagina: {BASE_URL}")
    main_soup = get_soup(BASE_URL)
    if not main_soup:
        print("FOUT: Kan hoofdpagina niet ophalen.")
        return [], []

    subpage_items = []
    document_items = []

    # Verzamel subpagina's
    subpage_urls = get_subpage_urls(main_soup)
    print(f"Gevonden subpagina's: {len(subpage_urls)}")

    for subpage_url in tqdm(subpage_urls, desc="Subpagina's scannen"):
        soup = get_soup(subpage_url)
        if not soup:
            continue

        sectie = subpage_url.split("/")[-1].replace("gr26-", "").replace("-", " ")
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else sectie

        subpage_items.append({
            "url": subpage_url,
            "title": title,
            "type": "subpagina",
            "sectie": sectie,
            "_soup": soup,  # Bewaar voor later gebruik
        })

        # Verzamel document-links
        docs = get_document_links(soup, subpage_url)
        document_items.extend(docs)

    # Dedupliceer documenten
    seen = set()
    unique_docs = []
    for doc in document_items:
        if doc["url"] not in seen:
            seen.add(doc["url"])
            unique_docs.append(doc)

    print(f"Totaal unieke document-links: {len(unique_docs)}")
    return subpage_items, unique_docs


def find_new_items(
    subpage_items: list[dict],
    document_items: list[dict],
    existing_metadata: list[dict],
) -> list[dict]:
    """Vergelijk met bestaande metadata en retourneer alleen nieuwe items."""
    existing_urls = {item["url"] for item in existing_metadata}

    new_items = []

    # Check subpagina's
    for item in subpage_items:
        if item["url"] not in existing_urls:
            new_items.append(item)

    # Check documenten
    for item in document_items:
        if item["url"] not in existing_urls:
            new_items.append(item)

    return new_items


def download_new_items(new_items: list[dict]) -> list[dict]:
    """Download HTML en PDF's voor nieuwe items."""
    print(f"\n=== Stap 2: {len(new_items)} nieuwe items downloaden ===\n")

    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)

    processed = []

    for item in tqdm(new_items, desc="Downloaden"):
        url = item["url"]
        print(f"  Nieuw: {item.get('title', url)}")

        # Gebruik bestaande soup als die er is (van subpagina-scan)
        soup = item.pop("_soup", None)
        if soup is None:
            soup = get_soup(url)

        if soup is None:
            print(f"    Overgeslagen (kon niet ophalen)")
            continue

        # Sla HTML op
        html_path = save_html(url, soup)
        item["html_file"] = html_path

        if item.get("type") == "subpagina":
            item["has_page_content"] = True
        else:
            main_content = soup.find("main") or soup.find("article") or soup
            item["has_page_content"] = len(main_content.get_text(strip=True)) > 100

            # Download PDF's
            pdf_paths = download_pdfs_from_page(url, soup)
            if pdf_paths:
                item["pdf_files"] = pdf_paths
                item["pdf_file"] = pdf_paths[0]
                item["type"] = "pdf"
            elif "type" not in item:
                item["type"] = "webpagina"

            # Bepaal sectie
            found_page = item.get("found_on", "").split("/")[-1]
            if found_page and "sectie" not in item:
                item["sectie"] = found_page.replace("gr26-", "").replace("-", " ")

        processed.append(item)
        print(f"    OK: HTML + {len(item.get('pdf_files', []))} PDF('s)")

    return processed


def parse_new_items(new_metadata: list[dict], next_passage_id: int) -> list[dict]:
    """Parse nieuwe items naar passages."""
    print(f"\n=== Stap 3: Nieuwe bestanden parsen ===\n")

    import re

    all_passages = []

    for item in tqdm(new_metadata, desc="Parsen"):
        url = item.get("url", "")
        title = item.get("title", "")
        sectie = item.get("sectie", "")
        item_type = item.get("type", "")

        passages = []

        # Parse PDF's
        pdf_files = item.get("pdf_files", [])
        if not pdf_files:
            single = item.get("pdf_file")
            if single:
                pdf_files = [single]

        for pdf_file in pdf_files:
            if Path(pdf_file).exists():
                pdf_passages = parse_pdf(pdf_file)
                pdf_name = Path(pdf_file).stem
                for p in pdf_passages:
                    p["bron_bestand"] = pdf_name
                passages.extend(pdf_passages)

        # Parse HTML
        html_file = item.get("html_file")
        if html_file and Path(html_file).exists():
            html_passages = parse_html(html_file)
            if html_passages:
                if item_type in ("subpagina", "hoofdpagina"):
                    passages = html_passages
                elif not passages:
                    passages = html_passages
                else:
                    passages.extend(html_passages)

        if not passages:
            continue

        # Voeg metadata toe
        for passage in passages:
            passage["bron_url"] = url
            passage["titel"] = title
            passage["sectie"] = sectie
            passage["type"] = item_type

        # Opschonen
        for passage in passages:
            passage["text"] = strip_footer(passage["text"])

        passages = [
            p for p in passages
            if not is_boilerplate(p.get("heading", ""), p["text"])
        ]

        # Dedupliceer
        seen_texts = set()
        unique = []
        for p in passages:
            norm = re.sub(r"\s+", " ", p["text"]).strip()
            if norm not in seen_texts:
                seen_texts.add(norm)
                unique.append(p)
        passages = unique

        all_passages.extend(passages)

    # Geef passage-IDs
    for i, passage in enumerate(all_passages):
        passage["id"] = next_passage_id + i

    print(f"  Nieuwe passages: {len(all_passages)}")
    return all_passages


def index_new_passages(new_passages: list[dict]):
    """Maak chunks van nieuwe passages en voeg toe aan bestaande FAISS index."""
    print(f"\n=== Stap 4: Nieuwe passages indexeren ===\n")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Maak chunks
    new_chunks = []
    for passage in new_passages:
        text = passage["text"]
        heading = passage.get("heading", "")
        full_text = f"{heading}\n\n{text}" if heading else text

        text_chunks = split_into_chunks(full_text)
        for i, chunk_text in enumerate(text_chunks):
            new_chunks.append({
                "text": chunk_text,
                "bron_url": passage.get("bron_url", ""),
                "titel": passage.get("titel", ""),
                "sectie": passage.get("sectie", ""),
                "heading": heading,
                "type": passage.get("type", ""),
                "passage_id": passage.get("id", 0),
                "chunk_index": i,
            })

    if not new_chunks:
        print("  Geen nieuwe chunks om te indexeren.")
        return

    print(f"  Nieuwe chunks: {len(new_chunks)}")

    # Laad embedding model
    print(f"  Laden embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    # Genereer embeddings voor nieuwe chunks
    print("  Genereren embeddings...")
    texts = [chunk["text"] for chunk in new_chunks]
    new_embeddings = model.encode(
        texts,
        show_progress_bar=True,
        batch_size=64,
        normalize_embeddings=True,
    ).astype(np.float32)

    # Laad bestaande index en chunks, of maak nieuwe
    if FAISS_INDEX_FILE.exists() and CHUNKS_FILE.exists():
        print("  Laden bestaande FAISS index...")
        index = faiss.read_index(str(FAISS_INDEX_FILE))
        with open(CHUNKS_FILE, "rb") as f:
            existing_chunks = pickle.load(f)

        print(f"  Bestaande chunks: {len(existing_chunks)}")

        # Voeg nieuwe vectors toe
        index.add(new_embeddings)
        all_chunks = existing_chunks + new_chunks
    else:
        print("  Geen bestaande index gevonden, maak nieuwe aan...")
        dimension = new_embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(new_embeddings)
        all_chunks = new_chunks

    # Sla op
    faiss.write_index(index, str(FAISS_INDEX_FILE))
    with open(CHUNKS_FILE, "wb") as f:
        pickle.dump(all_chunks, f)

    print(f"  Totaal chunks in index: {len(all_chunks)}")


def run():
    """Voer de incrementele update uit."""
    print("\n" + "=" * 60)
    print("  INCREMENTELE UPDATE — Verkiezingen Chatbot")
    print("=" * 60 + "\n")

    # Laad bestaande data
    existing_metadata = load_existing_metadata()
    existing_passages = load_existing_passages()
    print(f"Bestaande metadata-items: {len(existing_metadata)}")
    print(f"Bestaande passages: {len(existing_passages)}")

    # Scan de toolkit
    subpage_items, document_items = discover_current_urls()
    if not subpage_items and not document_items:
        print("\nKon de toolkit niet scannen. Afgebroken.")
        return

    # Vind nieuwe items
    new_items = find_new_items(subpage_items, document_items, existing_metadata)

    if not new_items:
        print("\n✓ Geen nieuwe documenten gevonden. Alles is up-to-date!")
        return

    print(f"\n>>> {len(new_items)} nieuwe items gevonden! <<<\n")
    for item in new_items:
        print(f"  + {item.get('title', item['url'])}")

    # Download nieuwe bestanden
    new_metadata = download_new_items(new_items)

    if not new_metadata:
        print("\nGeen nieuwe bestanden succesvol gedownload.")
        return

    # Update metadata.json
    existing_metadata.extend(new_metadata)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_metadata, f, ensure_ascii=False, indent=2)
    print(f"\nMetadata bijgewerkt: {len(existing_metadata)} items totaal")

    # Parse nieuwe bestanden
    next_id = max((p["id"] for p in existing_passages), default=-1) + 1
    new_passages = parse_new_items(new_metadata, next_id)

    if not new_passages:
        print("\nGeen nieuwe passages na parsing.")
        return

    # Update passages.json
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    existing_passages.extend(new_passages)
    with open(PASSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_passages, f, ensure_ascii=False, indent=2)
    print(f"Passages bijgewerkt: {len(existing_passages)} totaal")

    # Index nieuwe passages
    index_new_passages(new_passages)

    # Samenvatting
    print("\n" + "=" * 60)
    print("  UPDATE VOLTOOID")
    print("=" * 60)
    print(f"  Nieuwe items gedownload:  {len(new_metadata)}")
    print(f"  Nieuwe passages geparsed: {len(new_passages)}")
    print(f"  Totaal passages:          {len(existing_passages)}")
    print(f"  FAISS index bijgewerkt")
    print("=" * 60)


if __name__ == "__main__":
    run()

"""
Indexer: splits passages in chunks, genereert embeddings, en slaat op in FAISS.

Gebruikt een lokaal meertalig sentence-transformers model.
"""

import json
import pickle
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

DATA_DIR = Path(__file__).parent.parent / "data"
PASSAGES_FILE = DATA_DIR / "clean" / "passages.json"
INDEX_DIR = Path(__file__).parent.parent / "index"
FAISS_INDEX_FILE = INDEX_DIR / "faiss.index"
CHUNKS_FILE = INDEX_DIR / "chunks.pkl"

# Meertalig model, werkt goed voor Nederlands
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Chunk instellingen
MAX_CHUNK_CHARS = 1500  # ~375 tokens
CHUNK_OVERLAP_CHARS = 200  # overlap tussen chunks


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS,
                      overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Splits tekst in overlappende chunks op alinea-grenzen."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # Als toevoegen van deze alinea de chunk te groot maakt
        if current_chunk and len(current_chunk) + len(para) + 1 > max_chars:
            chunks.append(current_chunk.strip())
            # Begin nieuwe chunk met overlap vanuit de vorige
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + "\n" + para
        else:
            current_chunk = current_chunk + "\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def run():
    """Bouw de FAISS index."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Laad passages
    print("Laden passages...")
    with open(PASSAGES_FILE, "r", encoding="utf-8") as f:
        passages = json.load(f)

    # Splits in chunks met metadata
    print("Splitsen in chunks...")
    chunks = []
    for passage in passages:
        text = passage["text"]
        heading = passage.get("heading", "")

        # Voeg heading toe aan de tekst voor betere context
        if heading:
            full_text = f"{heading}\n\n{text}"
        else:
            full_text = text

        text_chunks = split_into_chunks(full_text)

        for i, chunk_text in enumerate(text_chunks):
            chunks.append({
                "text": chunk_text,
                "bron_url": passage.get("bron_url", ""),
                "titel": passage.get("titel", ""),
                "sectie": passage.get("sectie", ""),
                "heading": heading,
                "type": passage.get("type", ""),
                "passage_id": passage.get("id", 0),
                "chunk_index": i,
            })

    print(f"Totaal chunks: {len(chunks)}")

    # Laad het embedding model
    print(f"\nLaden embedding model: {MODEL_NAME}")
    print("(eerste keer duurt langer vanwege download)")
    model = SentenceTransformer(MODEL_NAME)

    # Genereer embeddings
    print("\nGenereren embeddings...")
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        batch_size=64,
        normalize_embeddings=True,
    )

    # Bouw FAISS index
    print("\nBouwen FAISS index...")
    dimension = embeddings.shape[1]
    # Gebruik Inner Product (cosine similarity omdat embeddings genormaliseerd zijn)
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype(np.float32))

    # Sla op
    faiss.write_index(index, str(FAISS_INDEX_FILE))
    with open(CHUNKS_FILE, "wb") as f:
        pickle.dump(chunks, f)

    # Samenvatting
    print("\n" + "=" * 50)
    print("INDEXER VOLTOOID")
    print("=" * 50)
    print(f"Passages verwerkt:  {len(passages)}")
    print(f"Chunks gemaakt:     {len(chunks)}")
    print(f"Embedding dimensie: {dimension}")
    print(f"FAISS index:        {FAISS_INDEX_FILE}")
    print(f"Chunks metadata:    {CHUNKS_FILE}")

    # Test query
    print("\n--- Test query ---")
    test_query = "Hoe werkt stemmen per volmacht?"
    query_embedding = model.encode([test_query], normalize_embeddings=True)
    distances, indices = index.search(query_embedding.astype(np.float32), k=3)

    for rank, (dist, idx) in enumerate(zip(distances[0], indices[0]), 1):
        chunk = chunks[idx]
        print(f"\n#{rank} (score: {dist:.3f})")
        print(f"  Bron: {chunk['titel']}")
        print(f"  Sectie: {chunk['sectie']}")
        print(f"  Tekst: {chunk['text'][:150]}...")


if __name__ == "__main__":
    run()

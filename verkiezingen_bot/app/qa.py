"""
QA Backend: vraag-antwoord pipeline met bronvermelding.

Vraag → zoek relevante chunks (FAISS) → stuur naar Mistral (Ollama) → antwoord.
"""

import json
import pickle
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

import ollama

INDEX_DIR = Path(__file__).parent.parent / "index"
FAISS_INDEX_FILE = INDEX_DIR / "faiss.index"
CHUNKS_FILE = INDEX_DIR / "chunks.pkl"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL = "qwen2.5:3b"
TOP_K = 3  # Aantal relevante chunks om mee te sturen
MAX_CONTEXT_CHARS = 2000  # Beperk totale context voor snelheid

SYSTEM_PROMPT = """Je bent een assistent over de gemeenteraadsverkiezingen 2026. Beantwoord de vraag ALLEEN op basis van de bronpassages. Vermeld de bron. Als het antwoord er niet in staat, zeg: "Ik kan dit niet vinden in de Toolkit Verkiezingen." Antwoord beknopt in het Nederlands."""


class QAEngine:
    """Vraag-antwoord engine met RAG."""

    def __init__(self):
        self._model = None
        self._index = None
        self._chunks = None

    def _load(self):
        """Lazy loading van model en index."""
        if self._model is None:
            print("Laden embedding model...")
            self._model = SentenceTransformer(EMBEDDING_MODEL)

        if self._index is None:
            print("Laden FAISS index...")
            self._index = faiss.read_index(str(FAISS_INDEX_FILE))
            with open(CHUNKS_FILE, "rb") as f:
                self._chunks = pickle.load(f)

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """Zoek de meest relevante chunks voor een vraag."""
        self._load()
        query_embedding = self._model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)

        distances, indices = self._index.search(query_embedding, top_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            chunk = self._chunks[idx].copy()
            chunk["score"] = float(dist)
            results.append(chunk)

        return results

    def build_context(self, chunks: list[dict]) -> str:
        """Bouw de context-tekst op uit gevonden chunks, beperkt tot MAX_CONTEXT_CHARS."""
        context_parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            part = (
                f"[{i}] {chunk['titel']}\n"
                f"{chunk['text']}\n"
            )
            if total_chars + len(part) > MAX_CONTEXT_CHARS:
                # Voeg nog een afgekapt stuk toe als er ruimte is
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 100:
                    context_parts.append(part[:remaining] + "...")
                break
            context_parts.append(part)
            total_chars += len(part)
        return "\n".join(context_parts)

    def ask(self, question: str) -> dict:
        """
        Beantwoord een vraag op basis van de toolkit.

        Returns:
            dict met 'answer', 'sources', en 'chunks'
        """
        # Zoek relevante passages
        chunks = self.search(question)

        # Bouw context
        context = self.build_context(chunks)

        # Stel de prompt samen
        user_prompt = (
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG: {question}\n\n"
            f"Geef een antwoord op basis van bovenstaande passages. "
            f"Vermeld de bron(nen)."
        )

        # Stuur naar Mistral via Ollama
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        answer = response["message"]["content"]

        # Verzamel unieke bronnen
        seen = set()
        sources = []
        for chunk in chunks:
            key = chunk["bron_url"]
            if key and key not in seen:
                seen.add(key)
                sources.append({
                    "titel": chunk["titel"],
                    "url": chunk["bron_url"],
                    "sectie": chunk["sectie"],
                })

        return {
            "answer": answer,
            "sources": sources,
            "chunks": chunks,
        }

    def ask_stream(self, question: str):
        """
        Beantwoord een vraag met streaming output.

        Yields:
            str tokens van het antwoord
        """
        chunks = self.search(question)
        context = self.build_context(chunks)

        user_prompt = (
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG: {question}\n\n"
            f"Geef een antwoord op basis van bovenstaande passages. "
            f"Vermeld de bron(nen)."
        )

        stream = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )

        full_answer = ""
        for chunk_response in stream:
            token = chunk_response["message"]["content"]
            full_answer += token
            yield token

        # Verzamel bronnen
        seen = set()
        sources = []
        for chunk in chunks:
            key = chunk["bron_url"]
            if key and key not in seen:
                seen.add(key)
                sources.append({
                    "titel": chunk["titel"],
                    "url": chunk["bron_url"],
                    "sectie": chunk["sectie"],
                })

        # Yield bronnen als laatste
        yield "\n\n__SOURCES__" + json.dumps(sources, ensure_ascii=False)


# Voor gebruik vanuit command line
if __name__ == "__main__":
    import json

    engine = QAEngine()

    print("Verkiezingen Chatbot - typ 'stop' om te stoppen\n")
    while True:
        question = input("\nVraag: ").strip()
        if question.lower() in ("stop", "quit", "exit"):
            break
        if not question:
            continue

        print("\nAntwoord wordt gegenereerd...\n")
        result = engine.ask(question)

        print(result["answer"])
        print("\n--- Bronnen ---")
        for src in result["sources"]:
            print(f"  - {src['titel']}")
            print(f"    {src['url']}")

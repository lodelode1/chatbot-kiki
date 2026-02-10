"""
QA Backend: vraag-antwoord pipeline met bronvermelding.

Vraag → hybride zoeken (FAISS + keyword) → stuur naar LLM (OpenRouter) → antwoord.
Kan later eenvoudig omgeschakeld worden naar lokale Ollama.
"""

import json
import os
import pickle
import re
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer

# Laad .env
load_dotenv(Path(__file__).parent.parent / ".env")

INDEX_DIR = Path(__file__).parent.parent / "index"
FAISS_INDEX_FILE = INDEX_DIR / "faiss.index"
CHUNKS_FILE = INDEX_DIR / "chunks.pkl"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# LLM configuratie — schakel hier tussen online en lokaal
# Online (OpenRouter):
LLM_MODEL = "mistralai/ministral-8b-2512"
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Lokaal (Ollama) — uncomment deze regels als je een GPU hebt:
# LLM_MODEL = "mistral"
# LLM_BASE_URL = "http://localhost:11434/v1"
# LLM_API_KEY = "ollama"

TOP_K = 10
MAX_CONTEXT_CHARS = 10000
MIN_SCORE = 0.30

SYSTEM_PROMPT = """Je bent Kiki, een vriendelijke en deskundige assistent over de gemeenteraadsverkiezingen 2026 in Nederland. Je helpt medewerkers van gemeenten met vragen over het verkiezingsproces op basis van de Toolkit Verkiezingen van de Kiesraad.

REGELS:
1. Baseer je antwoord UITSLUITEND op de aangeleverde bronpassages. Verzin geen informatie die niet in de bronnen staat.
2. Geef een BEKNOPT en direct antwoord. Kom meteen ter zake. Begin niet met "Op basis van de bronnen..." of vergelijkbare inleidingen.
3. Gebruik opsommingen alleen als de vraag om meerdere punten vraagt.
4. Als het antwoord niet in de bronnen te vinden is, zeg dan: "Dat kan ik niet vinden in de Toolkit Verkiezingen."
5. Antwoord altijd in het Nederlands.
6. Verwijs naar documenten bij naam, bijvoorbeeld: (zie Instructie Stembureauleden, sectie 'Stemmen bij volmacht'). Verwijs NOOIT naar "passage 1" of "bron 2".
7. Als de bronnen specifieke getallen, modelnummers of datums bevatten, neem deze letterlijk over — parafraseer geen cijfers.
8. Zet aan het eind een korte bronvermelding: [Bron: documentnaam - sectie]"""


class QAEngine:
    """Vraag-antwoord engine met RAG."""

    def __init__(self):
        self._model = None
        self._index = None
        self._chunks = None
        self._llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

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

    def _extract_keywords(self, query: str) -> list[str]:
        """Haal belangrijke zoektermen uit de vraag."""
        stopwoorden = {
            "de", "het", "een", "van", "in", "is", "op", "te", "dat", "die",
            "er", "en", "voor", "aan", "met", "als", "om", "bij", "ook",
            "nog", "wel", "niet", "maar", "dan", "wat", "hoe", "wie", "waar",
            "wanneer", "hoeveel", "welk", "welke", "kan", "kun", "moet",
            "worden", "wordt", "zijn", "ben", "was", "werd", "heeft", "hebben",
            "ik", "je", "we", "ze", "dit", "deze", "die", "daar", "hier",
            "zo", "al", "naar", "over", "door", "tot", "uit",
        }
        keywords = []

        # Herken modelnummers als geheel (bijv. "N 10-2", "Na 31-1", "I 4", "L 8")
        model_pattern = re.findall(
            r"\b([A-Z](?:a)?)\s+(\d[\d\-]*)\b", query, re.IGNORECASE
        )
        for letter, num in model_pattern:
            keywords.append(f"{letter.upper()} {num}".lower())

        # Overige woorden
        woorden = re.findall(r"[a-zA-Z0-9À-ÿ][\w\-]*", query.lower())
        for w in woorden:
            if w not in stopwoorden and len(w) > 1 and w not in keywords:
                keywords.append(w)

        return keywords

    def _keyword_search(self, keywords: list[str], top_k: int) -> list[dict]:
        """Zoek chunks die query-keywords bevatten."""
        if not keywords:
            return []

        scored = []
        for i, chunk in enumerate(self._chunks):
            text_lower = chunk["text"].lower()
            titel_lower = chunk.get("titel", "").lower()
            heading_lower = chunk.get("heading", "").lower()

            matches = 0
            for kw in keywords:
                if kw in text_lower or kw in titel_lower or kw in heading_lower:
                    matches += 1

            if matches > 0:
                # Score: fractie van matchende keywords
                score = matches / len(keywords)
                result = chunk.copy()
                result["score"] = score
                result["_chunk_idx"] = i
                scored.append(result)

        # Sorteer op score (meer matches = hoger)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """Hybride zoeken: combineer FAISS (semantisch) met keyword matching."""
        self._load()

        # 1. Semantisch zoeken (breed, zonder MIN_SCORE filter)
        query_embedding = self._model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)
        distances, indices = self._index.search(query_embedding, top_k * 5)

        semantic_results = {}
        for dist, idx in zip(distances[0], indices[0]):
            semantic_results[int(idx)] = float(dist)

        # 2. Keyword zoeken
        keywords = self._extract_keywords(query)
        keyword_results = self._keyword_search(keywords, top_k * 3)
        keyword_scores = {r["_chunk_idx"]: r["score"] for r in keyword_results}

        # 3. Combineer: alle unieke chunk indices
        all_indices = set(semantic_results.keys()) | set(keyword_scores.keys())

        combined = []
        for idx in all_indices:
            sem_score = semantic_results.get(idx, 0.0)
            kw_score = keyword_scores.get(idx, 0.0)

            # Hybride score: semantisch dominant, keyword als tiebreaker
            # Tenzij semantisch faalt en keyword sterk matcht
            if kw_score >= 0.5 and sem_score < MIN_SCORE:
                # Keyword-dominant: semantisch faalt, keyword neemt over
                final_score = kw_score * 0.55 + sem_score * 0.45
            else:
                # Normaal: semantisch dominant met kleine keyword boost
                final_score = sem_score * 0.85 + kw_score * 0.15

            if final_score < MIN_SCORE * 0.5:
                continue

            chunk = self._chunks[idx].copy()
            chunk["score"] = final_score
            combined.append(chunk)

        # Sorteer op gecombineerde score
        combined.sort(key=lambda x: x["score"], reverse=True)
        return combined[:top_k]

    def build_context(self, chunks: list[dict]) -> str:
        """Bouw de context-tekst op uit gevonden chunks, beperkt tot MAX_CONTEXT_CHARS."""
        context_parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            part = (
                f"--- Document: {chunk['titel']} | Sectie: {chunk['sectie']} ---\n"
                f"{chunk['text']}\n"
            )
            if total_chars + len(part) > MAX_CONTEXT_CHARS:
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 100:
                    context_parts.append(part[:remaining] + "...")
                break
            context_parts.append(part)
            total_chars += len(part)
        return "\n".join(context_parts)

    def _get_sources(self, chunks: list[dict]) -> list[dict]:
        """Verzamel unieke bronnen uit chunks."""
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
        return sources

    def ask(self, question: str) -> dict:
        """
        Beantwoord een vraag op basis van de toolkit.

        Returns:
            dict met 'answer', 'sources', en 'chunks'
        """
        chunks = self.search(question)
        context = self.build_context(chunks)

        user_prompt = (
            f"Hieronder staan passages uit de Toolkit Verkiezingen van de Kiesraad.\n\n"
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG VAN DE GEBRUIKER: {question}\n\n"
            f"Geef een beknopt antwoord op basis van de bovenstaande bronnen. "
            f"Verwijs naar documentnaam en sectie, niet naar 'passage' nummers."
        )

        response = self._llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        answer = response.choices[0].message.content

        return {
            "answer": answer,
            "sources": self._get_sources(chunks),
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
            f"Hieronder staan passages uit de Toolkit Verkiezingen van de Kiesraad.\n\n"
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG VAN DE GEBRUIKER: {question}\n\n"
            f"Geef een beknopt antwoord op basis van de bovenstaande bronnen. "
            f"Verwijs naar documentnaam en sectie, niet naar 'passage' nummers."
        )

        stream = self._llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            temperature=0.3,
        )

        for chunk_response in stream:
            if chunk_response.choices[0].delta.content:
                yield chunk_response.choices[0].delta.content

        # Yield bronnen als laatste
        yield "\n\n__SOURCES__" + json.dumps(
            self._get_sources(chunks), ensure_ascii=False
        )


# Voor gebruik vanuit command line
if __name__ == "__main__":
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

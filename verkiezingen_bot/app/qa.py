"""
QA Backend: vraag-antwoord pipeline met bronvermelding.

Vraag → hybride zoeken (FAISS + keyword) → re-rank → stuur naar LLM → antwoord.
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
from sentence_transformers import CrossEncoder, SentenceTransformer

# Laad .env
load_dotenv(Path(__file__).parent.parent / ".env")

INDEX_DIR = Path(__file__).parent.parent / "index"
FAISS_INDEX_FILE = INDEX_DIR / "faiss.index"
CHUNKS_FILE = INDEX_DIR / "chunks.pkl"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# Retrieval instellingen
RERANK_CANDIDATES = 25  # Breed ophalen voor re-ranking (lager = sneller op CPU)

# LLM configuratie — OpenRouter met Llama 3.3 70B (Meta, open-source)
LLM_MODEL = "meta-llama/llama-3.3-70b-instruct"
LLM_BASE_URL = "https://openrouter.ai/api/v1"


def _get_api_key():
    """Haal API key op uit .env (lokaal) of st.secrets (Streamlit Cloud)."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["OPENROUTER_API_KEY"]
        except Exception:
            pass
    return key

TOP_K = 10
MAX_CONTEXT_CHARS = 10000
MIN_SCORE = 0.30

SYSTEM_PROMPT = """Je bent Kiki, een vriendelijke en deskundige assistent over de gemeenteraadsverkiezingen 2026 in Nederland. Je helpt medewerkers van gemeenten met vragen over het verkiezingsproces op basis van de Toolkit Verkiezingen van de Kiesraad.

REGELS:
1. Baseer je antwoord UITSLUITEND op de aangeleverde bronpassages. Verzin geen informatie die niet in de bronnen staat.
2. Geef een helder en bondig antwoord van 2 tot 5 zinnen. Kom meteen ter zake — geen inleidingen. Alleen bij complexe procedures mag je iets langer uitweiden.
3. Gebruik opsommingen als dat de leesbaarheid verbetert.
4. Als het antwoord niet in de bronnen te vinden is, zeg dan: "Dat kan ik niet vinden in de Toolkit Verkiezingen."
5. Antwoord altijd in het Nederlands.
6. Als de bronnen specifieke getallen, modelnummers of datums bevatten, neem deze letterlijk over — parafraseer geen cijfers."""


class QAEngine:
    """Vraag-antwoord engine met RAG."""

    def __init__(self):
        self._model = None
        self._reranker = None
        self._index = None
        self._chunks = None
        self._llm = OpenAI(base_url=LLM_BASE_URL, api_key=_get_api_key())

    def _load(self):
        """Lazy loading van model, re-ranker en index."""
        if self._model is None:
            print("Laden embedding model...")
            self._model = SentenceTransformer(EMBEDDING_MODEL)

        if self._reranker is None:
            print("Laden re-ranker model...")
            self._reranker = CrossEncoder(RERANKER_MODEL)

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
        """Hybride zoeken + re-ranking voor maximale precisie."""
        self._load()

        # 1. Semantisch zoeken — breed net ophalen
        query_embedding = self._model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)
        distances, indices = self._index.search(
            query_embedding, RERANK_CANDIDATES
        )

        candidate_indices = set()
        for idx in indices[0]:
            candidate_indices.add(int(idx))

        # 2. Keyword zoeken — vult gaten aan die semantisch mist
        keywords = self._extract_keywords(query)
        keyword_results = self._keyword_search(keywords, RERANK_CANDIDATES)
        for r in keyword_results:
            candidate_indices.add(r["_chunk_idx"])

        # 3. Re-rank alle kandidaten met cross-encoder
        candidate_list = list(candidate_indices)
        pairs = [
            (query, self._chunks[idx]["text"]) for idx in candidate_list
        ]
        rerank_scores = self._reranker.predict(pairs)

        # 4. Combineer en sorteer op re-rank score
        combined = []
        for idx, score in zip(candidate_list, rerank_scores):
            chunk = self._chunks[idx].copy()
            chunk["score"] = float(score)
            combined.append(chunk)

        combined.sort(key=lambda x: x["score"], reverse=True)
        return combined[:top_k]

    def build_context(self, chunks: list[dict]) -> str:
        """Bouw de context-tekst op uit genummerde chunks, beperkt tot MAX_CONTEXT_CHARS."""
        context_parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            part = f"[{i}]\n{chunk['text']}\n"
            if total_chars + len(part) > MAX_CONTEXT_CHARS:
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 100:
                    context_parts.append(part[:remaining] + "...")
                break
            context_parts.append(part)
            total_chars += len(part)
        return "\n".join(context_parts)

    def _get_sources_by_indices(self, chunks: list[dict], indices: list[int]) -> list[dict]:
        """Verzamel bronnen op basis van passage-nummers die de LLM heeft aangegeven."""
        seen = set()
        sources = []
        for idx in indices:
            if idx < 0 or idx >= len(chunks):
                continue
            chunk = chunks[idx]
            key = chunk["bron_url"]
            if key and key not in seen:
                seen.add(key)
                sources.append({
                    "titel": chunk["titel"],
                    "url": chunk["bron_url"],
                    "sectie": chunk["sectie"],
                })
        return sources

    def _parse_used_passages(self, answer: str) -> tuple[str, list[int]]:
        """Haal passage-nummers uit het LLM-antwoord en strip die regel."""
        # Zoek patroon zoals "GEBRUIKTE PASSAGES: 1, 3, 5" of "GEBRUIKTE PASSAGES: [1, 3]"
        match = re.search(r"GEBRUIKTE PASSAGES:\s*\[?([\d,\s]+)\]?", answer, re.IGNORECASE)
        if match:
            nums = re.findall(r"\d+", match.group(1))
            indices = [int(n) - 1 for n in nums]  # 1-indexed → 0-indexed
            clean = answer[:match.start()].strip()
            return clean, indices
        return answer.strip(), []

    def ask(self, question: str) -> dict:
        """
        Beantwoord een vraag op basis van de toolkit.

        Returns:
            dict met 'answer', 'sources', en 'chunks'
        """
        chunks = self.search(question)
        context = self.build_context(chunks)

        user_prompt = (
            f"Hieronder staan genummerde passages uit de Toolkit Verkiezingen.\n\n"
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG VAN DE GEBRUIKER: {question}\n\n"
            f"Geef een helder en bondig antwoord op basis van de bovenstaande bronnen.\n"
            f"Sluit af met exact deze regel: GEBRUIKTE PASSAGES: [nummers]"
        )

        try:
            response = self._llm.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            answer = response.choices[0].message.content
            answer, used_indices = self._parse_used_passages(answer)
        except Exception as e:
            answer = f"Er ging iets mis bij het genereren van het antwoord: {e}"
            used_indices = []

        # Bronnen op basis van wat de LLM daadwerkelijk gebruikte
        if used_indices:
            sources = self._get_sources_by_indices(chunks, used_indices)
        else:
            # Fallback: top-1 bron als de LLM geen passages aangaf
            sources = self._get_sources_by_indices(chunks, [0])

        return {
            "answer": answer,
            "sources": sources,
            "chunks": chunks,
        }

    def ask_detailed(self, question: str, short_answer: str) -> dict:
        """
        Geef een uitgebreider antwoord op dezelfde vraag.

        Hergebruikt dezelfde zoekresultaten maar vraagt de LLM om meer detail.
        """
        chunks = self.search(question)
        context = self.build_context(chunks)

        user_prompt = (
            f"Hieronder staan genummerde passages uit de Toolkit Verkiezingen.\n\n"
            f"BRONPASSAGES:\n\n{context}\n\n"
            f"VRAAG VAN DE GEBRUIKER: {question}\n\n"
            f"Je gaf eerder dit korte antwoord: \"{short_answer}\"\n\n"
            f"Geef nu een uitgebreider en volledig antwoord. Leg de procedure stap voor stap uit "
            f"en behandel relevante details, uitzonderingen en aandachtspunten.\n"
            f"Sluit af met exact deze regel: GEBRUIKTE PASSAGES: [nummers]"
        )

        try:
            response = self._llm.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            answer = response.choices[0].message.content
            answer, used_indices = self._parse_used_passages(answer)
        except Exception as e:
            answer = f"Er ging iets mis bij het genereren van het antwoord: {e}"
            used_indices = []

        if used_indices:
            sources = self._get_sources_by_indices(chunks, used_indices)
        else:
            sources = self._get_sources_by_indices(chunks, [0])

        return {
            "answer": answer,
            "sources": sources,
            "chunks": chunks,
        }


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

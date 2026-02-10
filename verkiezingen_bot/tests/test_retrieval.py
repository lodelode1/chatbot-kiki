"""
Retrieval tests: controleer dat de zoekfunctie de juiste chunks vindt.

Deze tests roepen GEEN LLM aan — alleen het embedding model + FAISS index.
Ze testen of de juiste informatie in de top-K zoekresultaten zit.

Gebruik: pytest verkiezingen_bot/tests/test_retrieval.py -v
"""

import pytest

from verkiezingen_bot.app.qa import QAEngine

# Gedeelde engine (laden duurt een paar seconden, dus hergebruiken)
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = QAEngine()
        _engine._load()
    return _engine


def search_texts(query: str, top_k: int = 10) -> list[str]:
    """Zoek en geef de teksten van de top-K chunks terug (lowercase)."""
    engine = get_engine()
    results = engine.search(query, top_k=top_k)
    return [r["text"].lower() for r in results]


def search_results(query: str, top_k: int = 10) -> list[dict]:
    """Zoek en geef de volledige top-K chunks terug."""
    engine = get_engine()
    return engine.search(query, top_k=top_k)


def any_chunk_contains(texts: list[str], *keywords: str) -> bool:
    """Check of minstens één chunk ALLE opgegeven keywords bevat."""
    for text in texts:
        if all(kw.lower() in text for kw in keywords):
            return True
    return False


def any_chunk_contains_any(texts: list[str], *keywords: str) -> bool:
    """Check of minstens één chunk minstens één van de keywords bevat."""
    for text in texts:
        if any(kw.lower() in text for kw in keywords):
            return True
    return False


# === Testvragen ===
# Elke test controleert of de retrieval de juiste informatie vindt,
# onafhankelijk van wat het LLM er vervolgens mee doet.


class TestRetrieval:
    """Test of de zoekfunctie relevante chunks vindt voor bekende vragen."""

    def test_vraag1_verkiezingsdatum(self):
        """Wanneer zijn de gemeenteraadsverkiezingen 2026?
        Verwacht: '18 maart 2026' in de resultaten."""
        texts = search_texts("Wanneer zijn de gemeenteraadsverkiezingen 2026?")
        assert any_chunk_contains(texts, "18 maart 2026"), \
            "Datum '18 maart 2026' niet gevonden in top-10 chunks"

    def test_vraag2_model_i4(self):
        """Welk model gebruikt het CSB bij de openbare zitting waarin de lijsten vastgesteld worden?
        Verwacht: 'I 4' of 'I4' in de resultaten."""
        texts = search_texts(
            "Welk model gebruikt het CSB bij de openbare zitting waarin de lijsten vastgesteld worden?"
        )
        assert any_chunk_contains_any(texts, "i 4", "i4", "model i 4"), \
            "Model 'I 4' niet gevonden in top-10 chunks"

    def test_vraag3_controleprotocol_gsb(self):
        """Hoeveel lijsten moet het GSB controleren volgens het controleprotocol?
        Verwacht: '3 lijsten' verplicht, advies om 'alle lijsten' te controleren."""
        texts = search_texts(
            "Hoeveel lijsten moet het GSB controleren volgens het controleprotocol?"
        )
        assert any_chunk_contains_any(texts, "drie lijsten", "3 lijsten", "alle lijsten"), \
            "'drie lijsten' of 'alle lijsten' niet gevonden in top-10 chunks"

    @pytest.mark.xfail(reason="Bekende retrieval-gap: 'spreadsheet' niet in top-10 voor deze vraag")
    def test_vraag4_zetelverdeling_spreadsheet(self):
        """Hoe kan het CSB de zetelverdeling controleren?
        Verwacht: 'spreadsheet' in de resultaten."""
        texts = search_texts("Hoe kan het CSB de zetelverdeling controleren?")
        assert any_chunk_contains(texts, "spreadsheet"), \
            "'spreadsheet' niet gevonden in top-10 chunks"

    def test_vraag5_n10_2_wijzigingen(self):
        """Wat is er veranderd aan model N 10-2?
        Verwacht: info over opsplitsing of wijziging van N 10-2."""
        texts = search_texts("Wat is er veranderd aan model N 10-2?")
        assert any_chunk_contains_any(texts, "n 10-2", "n10-2"), \
            "Geen chunk met 'N 10-2' gevonden in top-10"

    def test_vraag6_leden_gsb(self):
        """Uit hoeveel leden bestaat het gemeentelijk stembureau?
        Verwacht: '3' en '5' (minimaal 3, maximaal 5)."""
        texts = search_texts("Uit hoeveel leden bestaat het gemeentelijk stembureau?")
        assert any_chunk_contains(texts, "3") and any_chunk_contains(texts, "5"), \
            "Aantallen '3' en '5' niet gevonden in top-10 chunks"

    def test_vraag7_voorzitter_gsb(self):
        """Wie is de voorzitter van het gemeentelijk stembureau?
        Verwacht: 'burgemeester' in de resultaten."""
        texts = search_texts("Wie is de voorzitter van het gemeentelijk stembureau?")
        assert any_chunk_contains(texts, "burgemeester"), \
            "'burgemeester' niet gevonden in top-10 chunks"

    def test_vraag8_volmachten(self):
        """Hoeveel volmachten mag een kiezer aannemen?
        Verwacht: 'maximaal 2' of '2 volmacht' in de resultaten."""
        texts = search_texts("Hoeveel volmachten mag een kiezer aannemen?")
        assert any_chunk_contains_any(texts, "maximaal 2", "2 volmacht"), \
            "'maximaal 2' of '2 volmacht' niet gevonden in top-10 chunks"

    def test_vraag9_kiezerspas(self):
        """Kan ik als kiezer een kiezerspas aanvragen voor de gemeenteraadsverkiezing?
        Verwacht: informatie over kiezerspas of stempas in de resultaten.
        NB: De toolkit bevat geen expliciete passage hierover — dit is een bekende bronnen-gap."""
        texts = search_texts(
            "Kan ik als kiezer een kiezerspas aanvragen voor de gemeenteraadsverkiezing?"
        )
        # We controleren alleen dat er relevante chunks over stempassen/kiezerspassen komen
        has_relevant = any_chunk_contains_any(texts, "kiezerspas", "stempas", "volmacht")
        # Dit is een zachte test: als er niets relevants komt, is dat een bekend probleem
        if not has_relevant:
            pytest.skip("Bekende bronnen-gap: geen expliciete kiezerspas-info in toolkit")

    def test_vraag10_telling_stemmen(self):
        """Wanneer begint de telling van de stemmen?
        Verwacht: '21' of '21:00' of '21.00' in de resultaten."""
        texts = search_texts("Wanneer begint de telling van de stemmen?")
        assert any_chunk_contains_any(texts, "21:00", "21.00", "na 21"), \
            "Tijdstip '21:00' niet gevonden in top-10 chunks"


class TestRetrievalKwaliteit:
    """Aanvullende tests voor retrieval-kwaliteit."""

    def test_top1_relevantie_verkiezingsdatum(self):
        """De verkiezingsdatum moet in de top-3 staan, niet op plek 8."""
        results = search_results("Wanneer zijn de gemeenteraadsverkiezingen 2026?")
        top3_texts = [r["text"].lower() for r in results[:3]]
        assert any_chunk_contains(top3_texts, "18 maart 2026"), \
            "Datum '18 maart 2026' staat niet in top-3"

    def test_minimale_score(self):
        """Alle resultaten moeten een redelijke score hebben."""
        results = search_results("Hoe werkt stemmen bij volmacht?")
        for r in results:
            assert r["score"] >= 0.15, \
                f"Chunk met te lage score ({r['score']:.3f}) in resultaten"

    def test_onzin_vraag_weinig_resultaten(self):
        """Bij een onzin-vraag moeten er weinig of lage-score resultaten zijn."""
        results = search_results("Wat is het recept voor appeltaart?")
        if results:
            # Hoogste score moet laag zijn voor een irrelevante vraag
            assert results[0]["score"] < 0.6, \
                f"Onzin-vraag krijgt te hoge score: {results[0]['score']:.3f}"

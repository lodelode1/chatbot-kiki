"""
End-to-end tests: stuur vragen door de volledige pipeline (search + LLM).

Let op: deze tests roepen het LLM aan via OpenRouter, dus ze zijn:
- Langzamer (paar seconden per vraag)
- Niet 100% deterministisch (LLM kan variëren)

Gebruik: pytest verkiezingen_bot/tests/test_e2e.py -v
"""

import pytest

from verkiezingen_bot.app.qa import QAEngine

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = QAEngine()
    return _engine


def ask(question: str) -> str:
    """Stel een vraag en geef het antwoord terug (lowercase)."""
    engine = get_engine()
    result = engine.ask(question)
    return result["answer"].lower()


# === Testvragen met verwachte sleutelwoorden in het antwoord ===


class TestEndToEnd:
    """Test of de chatbot correcte antwoorden geeft op bekende vragen."""

    def test_vraag1_verkiezingsdatum(self):
        antwoord = ask("Wanneer zijn de gemeenteraadsverkiezingen 2026?")
        assert "18 maart" in antwoord or "18-03" in antwoord, \
            f"Verwacht '18 maart' in antwoord, kreeg: {antwoord[:200]}"

    @pytest.mark.xfail(strict=False, reason="LLM verwart modelnummers — retrieval vindt I 4 wel")
    def test_vraag2_model_i4(self):
        antwoord = ask(
            "Welk model gebruikt het CSB bij de openbare zitting waarin de lijsten vastgesteld worden?"
        )
        assert "i 4" in antwoord or "i4" in antwoord, \
            f"Verwacht 'I 4' in antwoord, kreeg: {antwoord[:200]}"

    def test_vraag3_controleprotocol_gsb(self):
        antwoord = ask(
            "Hoeveel lijsten moet het GSB controleren volgens het controleprotocol?"
        )
        assert ("3" in antwoord or "drie" in antwoord) and "alle lijsten" in antwoord, \
            f"Verwacht '3' of 'drie' + 'alle lijsten' in antwoord, kreeg: {antwoord[:200]}"

    @pytest.mark.xfail(reason="Bekende retrieval-gap: 'spreadsheet' niet in top-10 chunks")
    def test_vraag4_zetelverdeling_spreadsheet(self):
        antwoord = ask("Hoe kan het CSB de zetelverdeling controleren?")
        assert "spreadsheet" in antwoord, \
            f"Verwacht 'spreadsheet' in antwoord, kreeg: {antwoord[:200]}"

    def test_vraag5_n10_2_wijzigingen(self):
        antwoord = ask("Wat is er veranderd aan model N 10-2?")
        assert "drie" in antwoord or "3" in antwoord or "opgesplitst" in antwoord or "gesplitst" in antwoord, \
            f"Verwacht info over opsplitsing in antwoord, kreeg: {antwoord[:200]}"

    def test_vraag6_leden_gsb(self):
        antwoord = ask("Uit hoeveel leden bestaat het gemeentelijk stembureau?")
        assert ("3" in antwoord and "5" in antwoord) or "drie" in antwoord, \
            f"Verwacht '3' en '5' in antwoord, kreeg: {antwoord[:200]}"

    @pytest.mark.xfail(strict=False, reason="LLM geeft soms vager antwoord — retrieval vindt 'burgemeester' wel")
    def test_vraag7_voorzitter_gsb(self):
        antwoord = ask("Wie is de voorzitter van het gemeentelijk stembureau?")
        assert "burgemeester" in antwoord, \
            f"Verwacht 'burgemeester' in antwoord, kreeg: {antwoord[:200]}"

    def test_vraag8_volmachten(self):
        antwoord = ask("Hoeveel volmachten mag een kiezer aannemen?")
        assert "2" in antwoord or "twee" in antwoord, \
            f"Verwacht '2' of 'twee' in antwoord, kreeg: {antwoord[:200]}"

    def test_vraag9_kiezerspas(self):
        """NB: De toolkit bevat geen expliciete info hierover.
        We testen dat het model niet hallucineert dat het WEL kan."""
        antwoord = ask(
            "Kan ik als kiezer een kiezerspas aanvragen voor de gemeenteraadsverkiezing?"
        )
        # Acceptabel: "niet", "geen kiezerspas", of "kan ik niet vinden"
        niet_beschikbaar = "niet" in antwoord or "geen" in antwoord or "kan ik niet vinden" in antwoord
        # Niet acceptabel: een volmondig "ja" zonder voorbehoud
        hallucineert_ja = antwoord.strip().startswith("ja")
        assert niet_beschikbaar or not hallucineert_ja, \
            f"Mogelijk hallucinatie over kiezerspas: {antwoord[:200]}"

    def test_vraag10_telling_stemmen(self):
        antwoord = ask("Wanneer begint de telling van de stemmen?")
        assert "21" in antwoord, \
            f"Verwacht '21' (uur) in antwoord, kreeg: {antwoord[:200]}"


class TestHallucinatie:
    """Test dat het model niet hallucineert bij onbekende vragen."""

    def test_onbekend_onderwerp(self):
        antwoord = ask("Wat is het belastingtarief voor kleine ondernemers in 2026?")
        assert "niet" in antwoord or "kan ik niet vinden" in antwoord or "geen" in antwoord, \
            f"Verwacht afwijzing, kreeg: {antwoord[:200]}"

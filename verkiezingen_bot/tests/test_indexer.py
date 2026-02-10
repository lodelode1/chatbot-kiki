"""
Tests voor de indexer: split_into_chunks.
"""

import pytest

from verkiezingen_bot.app.indexer import split_into_chunks


class TestSplitIntoChunks:
    def test_korte_tekst_geen_split(self):
        tekst = "Dit is een korte tekst."
        chunks = split_into_chunks(tekst, max_chars=1200)
        assert len(chunks) == 1
        assert chunks[0] == tekst

    def test_split_op_alinea_grenzen(self):
        # Maak tekst die langer is dan max_chars
        alineas = [f"Alinea {i}: " + "woord " * 30 for i in range(10)]
        tekst = "\n".join(alineas)
        chunks = split_into_chunks(tekst, max_chars=400, overlap=100)
        assert len(chunks) > 1
        # Elke chunk moet binnen de limiet vallen (met marge voor overlap)
        for chunk in chunks:
            assert len(chunk) < 800  # ruime marge

    def test_overlap_bevat_vorige_tekst(self):
        # Drie alinea's, elk 200 chars, max 300 → moet splitsen met overlap
        a1 = "A" * 200
        a2 = "B" * 200
        a3 = "C" * 200
        tekst = f"{a1}\n{a2}\n{a3}"
        chunks = split_into_chunks(tekst, max_chars=300, overlap=150)
        assert len(chunks) >= 2
        # Tweede chunk moet beginnen met tekst uit de eerste chunk (overlap)
        assert "A" in chunks[1], "Tweede chunk mist overlap uit eerste chunk"
        # Derde chunk moet B's bevatten (overlap uit tweede chunk)
        if len(chunks) >= 3:
            assert "B" in chunks[2], "Derde chunk mist overlap uit tweede chunk"

    def test_lege_tekst(self):
        chunks = split_into_chunks("", max_chars=1200)
        assert len(chunks) == 1

    def test_exact_op_grens(self):
        tekst = "x" * 1200
        chunks = split_into_chunks(tekst, max_chars=1200)
        assert len(chunks) == 1

    def test_net_over_grens(self):
        tekst = "x" * 600 + "\n" + "y" * 600 + "\n" + "z" * 100
        chunks = split_into_chunks(tekst, max_chars=700, overlap=100)
        assert len(chunks) >= 2

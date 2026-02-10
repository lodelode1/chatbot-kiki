"""
Tests voor de parser: clean_text, strip_footer, is_boilerplate.
"""

import pytest

from verkiezingen_bot.scraper.parser import clean_text, is_boilerplate, strip_footer


# === clean_text ===

class TestCleanText:
    def test_meerdere_spaties(self):
        assert clean_text("hallo   wereld") == "hallo wereld"

    def test_tabs_worden_spatie(self):
        assert clean_text("hallo\twereld") == "hallo wereld"

    def test_teveel_lege_regels(self):
        result = clean_text("regel 1\n\n\n\n\nregel 2")
        assert result == "regel 1\n\nregel 2"

    def test_strip_witruimte_per_regel(self):
        result = clean_text("  regel 1  \n  regel 2  ")
        assert result == "regel 1\nregel 2"

    def test_lege_string(self):
        assert clean_text("") == ""

    def test_alleen_witruimte(self):
        assert clean_text("   \n\n   ") == ""


# === strip_footer ===

class TestStripFooter:
    def test_meer_informatie_footer(self):
        tekst = "Belangrijke inhoud.\n\nMeer informatie\nMeer informatie over het organiseren van verkiezingen vindt u op kiesraad.nl."
        result = strip_footer(tekst)
        assert result == "Belangrijke inhoud."

    def test_nieuwsbrief_footer(self):
        tekst = "Inhoud van nieuwsbrief.\n\nWil je de Nieuwsbrief Verkiezingen zelf ook ontvangen? Meld je aan."
        result = strip_footer(tekst)
        assert result == "Inhoud van nieuwsbrief."

    def test_email_footer(self):
        tekst = "Bericht.\n\nDeze e-mail is verstuurd aan test@example.com"
        result = strip_footer(tekst)
        assert result == "Bericht."

    def test_geen_footer(self):
        tekst = "Gewone tekst zonder footer."
        assert strip_footer(tekst) == tekst

    def test_footer_aan_begin_blijft_leeg(self):
        # idx == 0 → wordt niet gestript (if idx > 0)
        tekst = "Meer informatie\nMeer informatie over het organiseren van verkiezingen"
        assert strip_footer(tekst) == tekst


# === is_boilerplate ===

class TestIsBoilerplate:
    def test_deel_deze_pagina_heading(self):
        assert is_boilerplate("Deel deze pagina", "Facebook Twitter LinkedIn") is True

    def test_deel_deze_pagina_tekst(self):
        assert is_boilerplate("", "Deel deze pagina via sociale media links") is True

    def test_te_kort(self):
        assert is_boilerplate("", "Kort.") is True
        assert is_boilerplate("", "x" * 49) is True

    def test_lang_genoeg(self):
        assert is_boilerplate("", "x" * 60) is False

    def test_pdf_nummers_artefact(self):
        # Meer dan 70% van de regels zijn alleen nummers
        regels = ["1", "2", "3", "4", "5", "6", "7", "naam", "8", "9"]
        tekst = "\n".join(regels)
        assert is_boilerplate("", tekst) is True

    def test_normale_tekst(self):
        tekst = "Het stembureau opent om 07:30 uur en sluit om 21:00 uur. Kiezers die op dat moment in het stemlokaal zijn, mogen nog stemmen."
        assert is_boilerplate("", tekst) is False

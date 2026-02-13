"""
Data Engine: text-to-SQL voor verkiezingsdata.

Stuurt een vraag + schema + few-shot voorbeelden naar de LLM,
voert de gegenereerde SQL uit op SQLite, en formuleert een antwoord.
"""

import os
import re
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(__file__).parent.parent / "data" / "verkiezingen.db"

LLM_MODEL = "meta-llama/llama-3.3-70b-instruct"
LLM_BASE_URL = "https://openrouter.ai/api/v1"

QUERY_TIMEOUT = 5  # seconden


def _get_api_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["OPENROUTER_API_KEY"]
        except Exception:
            pass
    return key


SCHEMA_DESCRIPTION = """
Je hebt toegang tot een SQLite database met verkiezingsuitslagen van de Tweede Kamerverkiezingen 2025 (TK2025).

=== TABELLEN ===

verkiezingen (id, verkiezing_code, naam, type, datum, aantal_zetels)
  -- 1 rij: de verkiezing zelf

partijen (id, verkiezing_id, partij_nr, naam, naam_kort)
  -- alle deelnemende partijen. Gebruik naam_kort voor filtering.
  -- Beschikbare naam_kort waarden: PVV, GL-PvdA, VVD, D66, BBB, CDA, SP, DENK, PvdD, FVD, SGP, CU, Volt, JA21, 50PLUS, NSC, BVNL, Piratenpartij, LEF, Samen1NL, PPNederland, De Groenen, Libertaire Partij, PvdS

kandidaten (id, verkiezing_id, partij_id, volgnr, naam, voornaam, initialen, tussenvoegsel, geslacht, woonplaats)
  -- alle kandidaten. naam = achternaam. volgnr = positie op de lijst.

gemeenten (id, verkiezing_id, gemeente_code, naam, kieskring_id, kieskring_naam, kiesgerechtigden)
  -- alle 346 gemeenten. kiesgerechtigden = totaal stemgerechtigde inwoners.

stembureaus (id, gemeente_id, stembureau_code, naam, postcode,
             uitgebrachte_stemmen, toegelaten_kiezers, getelde_stembiljetten,
             blanco, ongeldig,
             geldige_stempassen, geldige_volmachtbewijzen, geldige_kiezerspassen,
             meer_geteld, minder_geteld,
             meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
             te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
  -- 10.085 stembureaus.

stemmen_partij (stembureau_id, partij_id, stemmen)
  -- stemmen per partij per stembureau

zetels (verkiezing_id, partij_id, zetels)
  -- zetelverdeling

gekozen_kandidaten (verkiezing_id, partij_id, kandidaat_id, ranking)
  -- wie is gekozen

kieskringen (id, verkiezing_id, kieskring_code, naam,
             kiesgerechtigden, getelde_stembiljetten, blanco, ongeldig,
             geldige_volmachtbewijzen, geldige_kiezerspassen,
             meer_geteld, minder_geteld,
             meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
             te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
  -- 20 kieskringen (HSB-niveau). Officiële kieskring-totalen vastgesteld door het hoofdstembureau.

kieskring_stemmen_partij (kieskring_id, partij_id, stemmen)
  -- stemmen per partij per kieskring (HSB-niveau)

kieskring_stemmen_kandidaat (kieskring_id, kandidaat_id, stemmen)
  -- stemmen per kandidaat per kieskring (HSB-niveau)

csb_totalen (id, verkiezing_id,
             kiesgerechtigden, getelde_stembiljetten, blanco, ongeldig,
             geldige_volmachtbewijzen, geldige_kiezerspassen,
             meer_geteld, minder_geteld,
             meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
             te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
  -- 1 rij: het officiële landelijke totaal (CSB-niveau), vastgesteld door de Kiesraad.

csb_stemmen_partij (verkiezing_id, partij_id, stemmen)
  -- stemmen per partij landelijk (CSB-niveau)

csb_stemmen_kandidaat (verkiezing_id, kandidaat_id, stemmen)
  -- stemmen per kandidaat landelijk (CSB-niveau)

=== VIEWS (gebruik deze als ze handig zijn) ===

v_gemeente_partij (gemeente, gemeente_code, kieskring_naam, kiesgerechtigden, partij, partij_kort, stemmen)
  -- stemmen per partij per gemeente, al geaggregeerd over stembureaus

v_kieskring_partij (kieskring, kieskring_code, partij, partij_kort, stemmen)
  -- stemmen per partij per kieskring (HSB-niveau), direct uit de officiële kieskring-tellingen

v_stembureau_overzicht (id, stembureau, postcode, stembureau_code, gemeente, gemeente_code, kieskring_naam,
                        uitgebrachte_stemmen, toegelaten_kiezers, getelde_stembiljetten,
                        blanco, ongeldig, geldige_stempassen, geldige_volmachtbewijzen, geldige_kiezerspassen,
                        meer_geteld, minder_geteld, meegenomen_stembiljetten,
                        te_weinig_uitgereikte_stembiljetten, te_veel_uitgereikte_stembiljetten,
                        geen_verklaring, andere_verklaring, telverschil)
  -- stembureaus met gemeente/kieskring info + berekend telverschil

=== DATA-WOORDENBOEK ===

Begrippen:
- Kiesgerechtigden: het aantal mensen dat mag stemmen in een gemeente. Staat in tabel gemeenten.
- Toegelaten kiezers: het aantal mensen dat daadwerkelijk is komen stemmen. Staat in tabel stembureaus.
- Getelde stembiljetten: geldig getelde stemmen, exclusief blanco en ongeldig. Staat in tabel stembureaus.
- Opkomst: (getelde_stembiljetten + blanco + ongeldig) / kiesgerechtigden * 100. Aggregeer getelde_stembiljetten, blanco en ongeldig uit stembureaus en kiesgerechtigden uit gemeenten.
- Telverschil: het verschil tussen het aantal toegelaten kiezers en het totaal getelde biljetten bij een stembureau. Vastgelegd als meer_geteld en minder_geteld. Netto telverschil = meer_geteld - minder_geteld (kolom telverschil in v_stembureau_overzicht).
- HSB (hoofdstembureau): het stembureau op kieskringniveau dat de uitslag van alle gemeenten in die kieskring vaststelt.
- GSB (gemeentelijk stembureau): het orgaan dat de uitslag van de gehele gemeente bekendmaakt, de optelsom van alle stembureaus.
- CSB (centraal stembureau): de Kiesraad, stelt de landelijke uitslag vast.
- Kieskring: regionale indeling. Meerdere gemeenten vormen samen een kieskring.

Bijzonderheden in de data:
- NBSB: staat in de data als "gemeente" maar is geen echte gemeente. Het bevat stemmen die niet aan een fysiek stembureau zijn gekoppeld. Bij vragen over gemeenten moet NBSB worden uitgesloten, tenzij de gebruiker er expliciet naar vraagt. Filter met: WHERE gemeente != 'NBSB'.

Aggregatieniveaus (hiërarchie: stembureau → GSB → HSB → CSB):
- Stembureau-niveau: gebruik stembureaus, stemmen_partij, of v_stembureau_overzicht. NB: kandidaat-stemmen zijn NIET beschikbaar op stembureau-niveau.
- Gemeente-niveau (GSB): gebruik v_gemeente_partij voor stemmen per partij. Voor andere gemeente-aggregaties: groepeer stembureaus op gemeente_id.
- Kieskring-niveau (HSB): gebruik v_kieskring_partij of kieskringen + kieskring_stemmen_partij. Dit zijn de officiële HSB-totalen, NIET geaggregeerd vanuit gemeenten.
- Landelijk (CSB): gebruik csb_totalen voor totaalcijfers, csb_stemmen_partij voor stemmen per partij. Dit is het officiële landelijke totaal.
- Als de gebruiker "per gemeente" of "welke gemeente" vraagt, gebruik gemeente-niveau. Als ze "per stembureau" vraagt, gebruik stembureau-niveau. Als ze "per kieskring" vraagt, gebruik v_kieskring_partij of kieskringen.
- Voor vergelijkingen tussen niveaus: gebruik de officiële tabellen van elk niveau (bijv. HSB-stemmen vs opgetelde GSB-stemmen).
"""

FEW_SHOT_EXAMPLES = """
=== VOORBEELDEN ===

Vraag: Hoeveel stemmen kreeg de PVV?
SQL: SELECT SUM(stemmen) AS totaal_stemmen FROM stemmen_partij sp JOIN partijen p ON p.id = sp.partij_id WHERE p.naam_kort = 'PVV';

Vraag: Hoeveel stemmen kreeg de PVV in Amsterdam?
SQL: SELECT SUM(stemmen) AS stemmen FROM v_gemeente_partij WHERE gemeente = 'Amsterdam' AND partij_kort = 'PVV';

Vraag: Wat was de opkomst in Amsterdam?
SQL: SELECT g.naam AS gemeente, g.kiesgerechtigden, SUM(sb.getelde_stembiljetten + sb.blanco + sb.ongeldig) AS totaal_biljetten, ROUND(100.0 * SUM(sb.getelde_stembiljetten + sb.blanco + sb.ongeldig) / g.kiesgerechtigden, 1) AS opkomst_pct FROM gemeenten g JOIN stembureaus sb ON sb.gemeente_id = g.id WHERE g.naam = 'Amsterdam' GROUP BY g.id;

Vraag: Wat was de landelijke opkomst?
SQL: SELECT SUM(g.kiesgerechtigden) AS kiesgerechtigden, SUM(sb.getelde_stembiljetten + sb.blanco + sb.ongeldig) AS totaal_biljetten, ROUND(100.0 * SUM(sb.getelde_stembiljetten + sb.blanco + sb.ongeldig) / SUM(g.kiesgerechtigden), 1) AS opkomst_pct FROM gemeenten g JOIN stembureaus sb ON sb.gemeente_id = g.id WHERE g.naam != 'NBSB';

Vraag: Stembureaus met een telverschil groter dan 8
SQL: SELECT stembureau, gemeente, telverschil, toegelaten_kiezers FROM v_stembureau_overzicht WHERE ABS(telverschil) > 8 ORDER BY ABS(telverschil) DESC;

Vraag: Stembureaus waar blanco meer dan 2% van de toegelaten kiezers was
SQL: SELECT stembureau, gemeente, blanco, toegelaten_kiezers, ROUND(100.0 * blanco / toegelaten_kiezers, 2) AS blanco_pct FROM v_stembureau_overzicht WHERE toegelaten_kiezers > 0 AND blanco > 0.02 * toegelaten_kiezers ORDER BY blanco_pct DESC;

Vraag: Hoeveel zetels heeft D66?
SQL: SELECT p.naam_kort, z.zetels FROM zetels z JOIN partijen p ON p.id = z.partij_id WHERE p.naam_kort = 'D66';

Vraag: Top 5 kandidaten met de meeste voorkeurstemmen
SQL: SELECT k.voornaam, k.tussenvoegsel, k.naam, p.naam_kort, csk.stemmen FROM csb_stemmen_kandidaat csk JOIN kandidaten k ON k.id = csk.kandidaat_id JOIN partijen p ON p.id = k.partij_id ORDER BY csk.stemmen DESC LIMIT 5;

Vraag: Hoeveel stemmen kreeg de PVV in kieskring Utrecht?
SQL: SELECT stemmen FROM v_kieskring_partij WHERE kieskring = 'Utrecht' AND partij_kort = 'PVV';

Vraag: Stemmen per partij per kieskring
SQL: SELECT kieskring, partij_kort, stemmen FROM v_kieskring_partij ORDER BY kieskring, stemmen DESC;

Vraag: Wat is het officiële landelijke totaal aantal stemmen?
SQL: SELECT kiesgerechtigden, getelde_stembiljetten, blanco, ongeldig FROM csb_totalen;

Vraag: Officiële landelijke stemmen per partij
SQL: SELECT p.naam_kort, csp.stemmen FROM csb_stemmen_partij csp JOIN partijen p ON p.id = csp.partij_id ORDER BY csp.stemmen DESC;

Vraag: Welke kieskring had de meeste blanco stemmen?
SQL: SELECT naam AS kieskring, blanco FROM kieskringen ORDER BY blanco DESC LIMIT 1;
"""

SQL_SYSTEM_PROMPT = f"""Je bent een SQL-expert die vragen over Nederlandse verkiezingsuitslagen beantwoordt.

{SCHEMA_DESCRIPTION}

{FEW_SHOT_EXAMPLES}

=== INSTRUCTIES ===
1. Genereer ALLEEN een SELECT query. Nooit INSERT, UPDATE, DELETE, DROP, ALTER of andere mutaties.
2. Gebruik naam_kort voor partijnamen (bijv. 'PVV', 'GL-PvdA', 'VVD').
3. Gebruik de views (v_gemeente_partij, v_kieskring_partij, v_stembureau_overzicht) als ze handig zijn.
4. Gebruik GEEN commentaar of uitleg. Geef ALLEEN de SQL query terug.
5. Zorg dat de query correct SQLite-syntax gebruikt.
6. Raadpleeg het data-woordenboek voor begrippen, bijzonderheden en aggregatieniveaus.
7. Beperk resultaten tot maximaal 50 rijen met LIMIT tenzij de gebruiker anders vraagt.
"""

ANSWER_SYSTEM_PROMPT = """Je formuleert een antwoord op basis van data uit een verkiezingsdatabase.

Format (volg dit EXACT):
- Zin 1-2: beantwoord de vraag met de cijfers uit de data. Niets meer.
- Zin 3: leg kort uit wat er is opgezocht (bijv. "Hiervoor zijn alle stembureaus geteld waar het verschil niet nul was.").
- STOP daarna. Geen interpretatie, geen duiding, geen extra context.

Voorbeeld:
Vraag: Hoeveel stemmen kreeg de PVV in Amsterdam?
Data: stemmen = 29546
Antwoord: De PVV kreeg 29.546 stemmen in Amsterdam. Hiervoor zijn de stemmen van alle stembureaus in de gemeente Amsterdam opgeteld.

Als de data leeg is, zeg dat er geen resultaten zijn gevonden."""


class DataEngine:
    """Text-to-SQL engine voor verkiezingsdata."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._llm = OpenAI(base_url=LLM_BASE_URL, api_key=_get_api_key())

    def _get_connection(self) -> sqlite3.Connection:
        """Open een read-only SQLite connectie."""
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=QUERY_TIMEOUT)
        conn.execute(f"PRAGMA busy_timeout = {QUERY_TIMEOUT * 1000}")
        return conn

    def _generate_sql(self, question: str) -> str:
        """Laat de LLM een SQL query genereren."""
        response = self._llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code blocks als de LLM die toevoegt
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Verwijder eerste en laatste ``` regel
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        # Strip eventuele SQL prefix
        if raw.upper().startswith("SQL:"):
            raw = raw[4:].strip()

        return raw

    def _validate_sql(self, sql: str) -> str | None:
        """Controleer of de query veilig is. Retourneert foutmelding of None."""
        sql_upper = sql.upper().strip()
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH"]
        for kw in forbidden:
            # Check als heel woord (niet als deel van kolomnaam)
            if re.search(rf"\b{kw}\b", sql_upper):
                return f"Onveilige query gedetecteerd: {kw} is niet toegestaan."
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            return "Query moet beginnen met SELECT of WITH."
        return None

    def _execute_sql(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Voer SQL uit en retourneer (kolommen, rijen)."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return columns, rows
        finally:
            conn.close()

    def _format_results(self, columns: list[str], rows: list[tuple], max_rows: int = 50) -> str:
        """Formatteer resultaten als leesbare tekst voor de LLM."""
        if not rows:
            return "Geen resultaten gevonden."

        lines = [" | ".join(columns)]
        lines.append("-" * len(lines[0]))
        for row in rows[:max_rows]:
            lines.append(" | ".join(str(v) if v is not None else "" for v in row))

        if len(rows) > max_rows:
            lines.append(f"... en nog {len(rows) - max_rows} rijen")

        return "\n".join(lines)

    def _generate_answer(self, question: str, result_text: str) -> str:
        """Laat de LLM een natuurlijk-taal antwoord formuleren."""
        response = self._llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Vraag: {question}\n\nData:\n{result_text}"},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    def ask_data(self, question: str) -> dict:
        """
        Beantwoord een datavraag.

        Returns:
            dict met 'answer', 'sql', 'data_table' (list of dicts), 'columns', 'error'
        """
        result = {"answer": "", "sql": "", "data_table": [], "columns": [], "error": None}

        try:
            # Stap 1: Genereer SQL
            sql = self._generate_sql(question)
            result["sql"] = sql

            # Stap 2: Valideer
            error = self._validate_sql(sql)
            if error:
                result["error"] = error
                result["answer"] = error
                return result

            # Stap 3: Voer uit
            try:
                columns, rows = self._execute_sql(sql)
            except Exception as e:
                # Stap 3b: Bij fout, 1 retry met foutmelding
                error_msg = str(e)
                retry_prompt = (
                    f"De vorige query gaf een fout:\n{error_msg}\n\n"
                    f"Oorspronkelijke vraag: {question}\n\n"
                    f"Genereer een correcte SQL query."
                )
                sql = self._generate_sql(retry_prompt)
                result["sql"] = sql

                error = self._validate_sql(sql)
                if error:
                    result["error"] = error
                    result["answer"] = error
                    return result

                columns, rows = self._execute_sql(sql)

            result["columns"] = columns
            result["data_table"] = [dict(zip(columns, row)) for row in rows[:100]]

            # Stap 4: Genereer antwoord
            result_text = self._format_results(columns, rows)
            result["answer"] = self._generate_answer(question, result_text)

        except Exception as e:
            result["error"] = str(e)
            result["answer"] = f"Er ging iets mis bij het beantwoorden van je datavraag: {e}"

        return result


if __name__ == "__main__":
    engine = DataEngine()

    print("Verkiezingen Data Engine - typ 'stop' om te stoppen\n")
    while True:
        question = input("\nDatavraag: ").strip()
        if question.lower() in ("stop", "quit", "exit"):
            break
        if not question:
            continue

        print("\nQuery wordt gegenereerd...\n")
        result = engine.ask_data(question)

        print(f"SQL: {result['sql']}\n")
        print(f"Antwoord: {result['answer']}")
        if result["error"]:
            print(f"\nFout: {result['error']}")
        if result["data_table"]:
            print(f"\n({len(result['data_table'])} rijen data)")

"""
EML-parser: leest Kiesraad EML-XML zip-bestanden en schrijft naar SQLite.

Gebruik:
    python -m verkiezingen_bot.data.eml_parser

Leest alle zip-bestanden uit verkiezingen_bot/data/EML/ en bouwt
verkiezingen_bot/data/verkiezingen.db.
"""

import re
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DATA_DIR = Path(__file__).parent
EML_DIR = DATA_DIR / "EML"
DB_PATH = DATA_DIR / "verkiezingen.db"

# XML namespaces in Kiesraad EML
NS = {
    "eml": "urn:oasis:names:tc:evs:schema:eml",
    "kr": "http://www.kiesraad.nl/extensions",
    "xnl": "urn:oasis:names:tc:ciq:xsdschema:xNL:2.0",
    "xal": "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
}

# Handmatige korte namen voor partijen
KORTE_NAMEN = {
    "PVV (Partij voor de Vrijheid)": "PVV",
    "GROENLINKS / Partij van de Arbeid (PvdA)": "GL-PvdA",
    "Staatkundig Gereformeerde Partij (SGP)": "SGP",
    "SP (Socialistische Partij)": "SP",
    "Partij voor de Dieren": "PvdD",
    "Forum voor Democratie": "FVD",
    "ChristenUnie": "CU",
}


def _korte_naam(volledige_naam: str) -> str:
    """Leidt een korte partijnaam af."""
    if volledige_naam in KORTE_NAMEN:
        return KORTE_NAMEN[volledige_naam]
    # Als de naam kort genoeg is, gebruik als-is
    if len(volledige_naam) <= 12:
        return volledige_naam
    # Probeer afkorting uit haakjes: "Partij X (PX)" -> "PX"
    m = re.search(r"\(([A-Z][A-Za-z0-9\-]+)\)", volledige_naam)
    if m:
        return m.group(1)
    return volledige_naam


def _text(elem, default=""):
    """Haal tekst uit een XML-element, of default als None."""
    return elem.text.strip() if elem is not None and elem.text else default


def _int(elem, default=0):
    """Haal integer waarde uit een XML-element."""
    t = _text(elem)
    return int(t) if t else default


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS verkiezingen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_code TEXT NOT NULL UNIQUE,
    naam            TEXT NOT NULL,
    type            TEXT NOT NULL,
    datum           TEXT NOT NULL,
    aantal_zetels   INTEGER
);

CREATE TABLE IF NOT EXISTS partijen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    partij_nr       INTEGER NOT NULL,
    naam            TEXT NOT NULL,
    naam_kort       TEXT NOT NULL,
    UNIQUE(verkiezing_id, partij_nr)
);

CREATE TABLE IF NOT EXISTS kandidaten (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    volgnr          INTEGER NOT NULL,
    naam            TEXT NOT NULL,
    voornaam        TEXT,
    initialen       TEXT,
    tussenvoegsel   TEXT,
    geslacht        TEXT,
    woonplaats      TEXT,
    UNIQUE(verkiezing_id, partij_id, volgnr)
);

CREATE TABLE IF NOT EXISTS gemeenten (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    gemeente_code   TEXT NOT NULL,
    naam            TEXT NOT NULL,
    kieskring_id    TEXT,
    kieskring_naam  TEXT,
    kiesgerechtigden INTEGER DEFAULT 0,
    UNIQUE(verkiezing_id, gemeente_code)
);

CREATE TABLE IF NOT EXISTS stembureaus (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    gemeente_id                     INTEGER NOT NULL REFERENCES gemeenten(id),
    stembureau_code                 TEXT NOT NULL,
    naam                            TEXT,
    postcode                        TEXT,
    uitgebrachte_stemmen            INTEGER DEFAULT 0,
    toegelaten_kiezers              INTEGER DEFAULT 0,
    getelde_stembiljetten           INTEGER DEFAULT 0,
    blanco                          INTEGER DEFAULT 0,
    ongeldig                        INTEGER DEFAULT 0,
    geldige_stempassen              INTEGER DEFAULT 0,
    geldige_volmachtbewijzen        INTEGER DEFAULT 0,
    geldige_kiezerspassen           INTEGER DEFAULT 0,
    meer_geteld                     INTEGER DEFAULT 0,
    minder_geteld                   INTEGER DEFAULT 0,
    meegenomen_stembiljetten        INTEGER DEFAULT 0,
    te_weinig_uitgereikte_stembiljetten INTEGER DEFAULT 0,
    te_veel_uitgereikte_stembiljetten   INTEGER DEFAULT 0,
    geen_verklaring                 INTEGER DEFAULT 0,
    andere_verklaring               INTEGER DEFAULT 0,
    UNIQUE(gemeente_id, stembureau_code)
);

CREATE TABLE IF NOT EXISTS stemmen_partij (
    stembureau_id   INTEGER NOT NULL REFERENCES stembureaus(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (stembureau_id, partij_id)
);

CREATE TABLE IF NOT EXISTS stemmen_kandidaat (
    stembureau_id   INTEGER NOT NULL REFERENCES stembureaus(id),
    kandidaat_id    INTEGER NOT NULL REFERENCES kandidaten(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (stembureau_id, kandidaat_id)
);

CREATE TABLE IF NOT EXISTS zetels (
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    zetels          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (verkiezing_id, partij_id)
);

CREATE TABLE IF NOT EXISTS gekozen_kandidaten (
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    kandidaat_id    INTEGER NOT NULL REFERENCES kandidaten(id),
    ranking         INTEGER,
    PRIMARY KEY (verkiezing_id, kandidaat_id)
);

CREATE TABLE IF NOT EXISTS kieskringen (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_id                   INTEGER NOT NULL REFERENCES verkiezingen(id),
    kieskring_code                  TEXT NOT NULL,
    naam                            TEXT NOT NULL,
    kiesgerechtigden                INTEGER DEFAULT 0,
    getelde_stembiljetten           INTEGER DEFAULT 0,
    blanco                          INTEGER DEFAULT 0,
    ongeldig                        INTEGER DEFAULT 0,
    geldige_volmachtbewijzen        INTEGER DEFAULT 0,
    geldige_kiezerspassen           INTEGER DEFAULT 0,
    meer_geteld                     INTEGER DEFAULT 0,
    minder_geteld                   INTEGER DEFAULT 0,
    meegenomen_stembiljetten        INTEGER DEFAULT 0,
    te_weinig_uitgereikte_stembiljetten INTEGER DEFAULT 0,
    te_veel_uitgereikte_stembiljetten   INTEGER DEFAULT 0,
    geen_verklaring                 INTEGER DEFAULT 0,
    andere_verklaring               INTEGER DEFAULT 0,
    UNIQUE(verkiezing_id, kieskring_code)
);

CREATE TABLE IF NOT EXISTS kieskring_stemmen_partij (
    kieskring_id    INTEGER NOT NULL REFERENCES kieskringen(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kieskring_id, partij_id)
);

CREATE TABLE IF NOT EXISTS kieskring_stemmen_kandidaat (
    kieskring_id    INTEGER NOT NULL REFERENCES kieskringen(id),
    kandidaat_id    INTEGER NOT NULL REFERENCES kandidaten(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kieskring_id, kandidaat_id)
);

CREATE TABLE IF NOT EXISTS csb_totalen (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    verkiezing_id                   INTEGER NOT NULL REFERENCES verkiezingen(id),
    kiesgerechtigden                INTEGER DEFAULT 0,
    getelde_stembiljetten           INTEGER DEFAULT 0,
    blanco                          INTEGER DEFAULT 0,
    ongeldig                        INTEGER DEFAULT 0,
    geldige_volmachtbewijzen        INTEGER DEFAULT 0,
    geldige_kiezerspassen           INTEGER DEFAULT 0,
    meer_geteld                     INTEGER DEFAULT 0,
    minder_geteld                   INTEGER DEFAULT 0,
    meegenomen_stembiljetten        INTEGER DEFAULT 0,
    te_weinig_uitgereikte_stembiljetten INTEGER DEFAULT 0,
    te_veel_uitgereikte_stembiljetten   INTEGER DEFAULT 0,
    geen_verklaring                 INTEGER DEFAULT 0,
    andere_verklaring               INTEGER DEFAULT 0,
    UNIQUE(verkiezing_id)
);

CREATE TABLE IF NOT EXISTS csb_stemmen_partij (
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    partij_id       INTEGER NOT NULL REFERENCES partijen(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (verkiezing_id, partij_id)
);

CREATE TABLE IF NOT EXISTS csb_stemmen_kandidaat (
    verkiezing_id   INTEGER NOT NULL REFERENCES verkiezingen(id),
    kandidaat_id    INTEGER NOT NULL REFERENCES kandidaten(id),
    stemmen         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (verkiezing_id, kandidaat_id)
);
"""

VIEWS = """
CREATE VIEW IF NOT EXISTS v_gemeente_partij AS
SELECT
    g.naam          AS gemeente,
    g.gemeente_code,
    g.kieskring_naam,
    g.kiesgerechtigden,
    p.naam          AS partij,
    p.naam_kort     AS partij_kort,
    SUM(sp.stemmen) AS stemmen
FROM stemmen_partij sp
JOIN stembureaus sb ON sb.id = sp.stembureau_id
JOIN gemeenten g ON g.id = sb.gemeente_id
JOIN partijen p ON p.id = sp.partij_id
GROUP BY g.id, p.id;

CREATE VIEW IF NOT EXISTS v_kieskring_partij AS
SELECT
    k.naam          AS kieskring,
    k.kieskring_code,
    p.naam          AS partij,
    p.naam_kort     AS partij_kort,
    ksp.stemmen
FROM kieskring_stemmen_partij ksp
JOIN kieskringen k ON k.id = ksp.kieskring_id
JOIN partijen p ON p.id = ksp.partij_id;

CREATE VIEW IF NOT EXISTS v_stembureau_overzicht AS
SELECT
    sb.id,
    sb.naam             AS stembureau,
    sb.postcode,
    sb.stembureau_code,
    g.naam              AS gemeente,
    g.gemeente_code,
    g.kieskring_naam,
    sb.uitgebrachte_stemmen,
    sb.toegelaten_kiezers,
    sb.getelde_stembiljetten,
    sb.blanco,
    sb.ongeldig,
    sb.geldige_stempassen,
    sb.geldige_volmachtbewijzen,
    sb.geldige_kiezerspassen,
    sb.meer_geteld,
    sb.minder_geteld,
    sb.meegenomen_stembiljetten,
    sb.te_weinig_uitgereikte_stembiljetten,
    sb.te_veel_uitgereikte_stembiljetten,
    sb.geen_verklaring,
    sb.andere_verklaring,
    (sb.meer_geteld - sb.minder_geteld) AS telverschil
FROM stembureaus sb
JOIN gemeenten g ON g.id = sb.gemeente_id;
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_partijen_verkiezing ON partijen(verkiezing_id);
CREATE INDEX IF NOT EXISTS idx_kandidaten_verkiezing ON kandidaten(verkiezing_id);
CREATE INDEX IF NOT EXISTS idx_kandidaten_partij ON kandidaten(partij_id);
CREATE INDEX IF NOT EXISTS idx_gemeenten_verkiezing ON gemeenten(verkiezing_id);
CREATE INDEX IF NOT EXISTS idx_stembureaus_gemeente ON stembureaus(gemeente_id);
CREATE INDEX IF NOT EXISTS idx_stemmen_partij_stembureau ON stemmen_partij(stembureau_id);
CREATE INDEX IF NOT EXISTS idx_stemmen_partij_partij ON stemmen_partij(partij_id);
CREATE INDEX IF NOT EXISTS idx_stemmen_kandidaat_stembureau ON stemmen_kandidaat(stembureau_id);
CREATE INDEX IF NOT EXISTS idx_stemmen_kandidaat_kandidaat ON stemmen_kandidaat(kandidaat_id);
CREATE INDEX IF NOT EXISTS idx_partijen_naam_kort ON partijen(naam_kort);
CREATE INDEX IF NOT EXISTS idx_gemeenten_naam ON gemeenten(naam);
CREATE INDEX IF NOT EXISTS idx_kieskringen_verkiezing ON kieskringen(verkiezing_id);
CREATE INDEX IF NOT EXISTS idx_kieskring_stemmen_partij_kieskring ON kieskring_stemmen_partij(kieskring_id);
CREATE INDEX IF NOT EXISTS idx_kieskring_stemmen_partij_partij ON kieskring_stemmen_partij(partij_id);
CREATE INDEX IF NOT EXISTS idx_kieskring_stemmen_kandidaat_kieskring ON kieskring_stemmen_kandidaat(kieskring_id);
CREATE INDEX IF NOT EXISTS idx_kieskring_stemmen_kandidaat_kandidaat ON kieskring_stemmen_kandidaat(kandidaat_id);
CREATE INDEX IF NOT EXISTS idx_csb_stemmen_partij_partij ON csb_stemmen_partij(partij_id);
CREATE INDEX IF NOT EXISTS idx_csb_stemmen_kandidaat_kandidaat ON csb_stemmen_kandidaat(kandidaat_id);
"""


# ---------------------------------------------------------------------------
# Parser functies
# ---------------------------------------------------------------------------

def _create_db(db_path: Path) -> sqlite3.Connection:
    """Maak database en schema aan."""
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _find_zips(eml_dir: Path) -> list[Path]:
    """Vind alle EML zip-bestanden."""
    zips = sorted(eml_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"Geen zip-bestanden gevonden in {eml_dir}")
    return zips


def _open_xml_from_zips(zips: list[zipfile.ZipFile], prefix: str) -> list[tuple[str, ET.Element]]:
    """Open alle XML-bestanden die beginnen met prefix uit de zipbestanden."""
    results = []
    for z in zips:
        for name in z.namelist():
            basename = name.split("/")[-1] if "/" in name else name
            if basename.startswith(prefix) and basename.endswith(".eml.xml"):
                data = z.read(name)
                root = ET.fromstring(data)
                results.append((name, root))
    return results


def parse_verkiezingsdefinitie(zips: list[zipfile.ZipFile], conn: sqlite3.Connection) -> int:
    """Parse Verkiezingsdefinitie → verkiezingen tabel. Retourneert verkiezing_id."""
    files = _open_xml_from_zips(zips, "Verkiezingsdefinitie")
    if not files:
        raise FileNotFoundError("Geen Verkiezingsdefinitie gevonden")

    _, root = files[0]
    election = root.find(".//eml:Election", NS)
    eid = election.find("eml:ElectionIdentifier", NS)

    code = eid.get("Id")
    naam = _text(eid.find("eml:ElectionName", NS))
    cat = _text(eid.find("eml:ElectionCategory", NS))
    datum = _text(eid.find("kr:ElectionDate", NS))
    zetels_el = election.find("kr:NumberOfSeats", NS)
    zetels = _int(zetels_el) if zetels_el is not None else None

    conn.execute(
        "INSERT INTO verkiezingen (verkiezing_code, naam, type, datum, aantal_zetels) VALUES (?,?,?,?,?)",
        (code, naam, cat, datum, zetels),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM verkiezingen WHERE verkiezing_code=?", (code,)).fetchone()
    verkiezing_id = row[0]
    print(f"  Verkiezing: {naam} ({code}), datum={datum}, zetels={zetels}")
    return verkiezing_id


def parse_kandidatenlijsten(
    zips: list[zipfile.ZipFile], conn: sqlite3.Connection, verkiezing_id: int
) -> dict[str, int]:
    """Parse Kandidatenlijsten → partijen + kandidaten. Retourneert {partij_nr: partij_id}."""
    files = _open_xml_from_zips(zips, "Kandidatenlijsten")
    if not files:
        raise FileNotFoundError("Geen Kandidatenlijsten gevonden")

    # Gebruik de eerste kieskring als bron (lijsten zijn gelijkluidend)
    _, root = files[0]
    contest = root.find(".//eml:CandidateList/eml:Election/eml:Contest", NS)

    partij_map = {}  # partij_nr -> partij_id
    kandidaat_count = 0

    for affiliation in contest.findall("eml:Affiliation", NS):
        aff_id_el = affiliation.find("eml:AffiliationIdentifier", NS)
        partij_nr = int(aff_id_el.get("Id"))
        naam = _text(aff_id_el.find("eml:RegisteredName", NS))
        naam_kort = _korte_naam(naam)

        conn.execute(
            "INSERT OR IGNORE INTO partijen (verkiezing_id, partij_nr, naam, naam_kort) VALUES (?,?,?,?)",
            (verkiezing_id, partij_nr, naam, naam_kort),
        )
        row = conn.execute(
            "SELECT id FROM partijen WHERE verkiezing_id=? AND partij_nr=?",
            (verkiezing_id, partij_nr),
        ).fetchone()
        partij_id = row[0]
        partij_map[str(partij_nr)] = partij_id

        # Kandidaten binnen deze partij
        for cand_el in affiliation.findall("eml:Candidate", NS):
            cid = cand_el.find("eml:CandidateIdentifier", NS)
            volgnr = int(cid.get("Id"))

            person = cand_el.find(".//xnl:PersonName", NS)
            achternaam = _text(person.find("xnl:LastName", NS)) if person is not None else ""
            voornaam = _text(person.find("xnl:FirstName", NS)) if person is not None else ""
            initialen = _text(person.find("xnl:NameLine[@NameType='Initials']", NS)) if person is not None else ""
            tussenvoegsel = _text(person.find("xnl:NamePrefix", NS)) if person is not None else ""

            geslacht = _text(cand_el.find("eml:Gender", NS))
            woonplaats_el = cand_el.find(".//xal:LocalityName", NS)
            woonplaats = _text(woonplaats_el) if woonplaats_el is not None else ""

            conn.execute(
                """INSERT OR IGNORE INTO kandidaten
                   (verkiezing_id, partij_id, volgnr, naam, voornaam, initialen, tussenvoegsel, geslacht, woonplaats)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (verkiezing_id, partij_id, volgnr, achternaam, voornaam, initialen, tussenvoegsel, geslacht, woonplaats),
            )
            kandidaat_count += 1

    conn.commit()
    print(f"  Partijen: {len(partij_map)}, Kandidaten: {kandidaat_count}")
    return partij_map


def _parse_uncounted(votes_el, ns: dict) -> dict:
    """Parse UncountedVotes en RejectedVotes uit een TotalVotes/ReportingUnitVotes element."""
    reason_map = {
        "geldige stempassen": "geldige_stempassen",
        "geldige volmachtbewijzen": "geldige_volmachtbewijzen",
        "geldige kiezerspassen": "geldige_kiezerspassen",
        "toegelaten kiezers": "toegelaten_kiezers",
        "meer getelde stembiljetten": "meer_geteld",
        "minder getelde stembiljetten": "minder_geteld",
        "meegenomen stembiljetten": "meegenomen_stembiljetten",
        "te weinig uitgereikte stembiljetten": "te_weinig_uitgereikte_stembiljetten",
        "te veel uitgereikte stembiljetten": "te_veel_uitgereikte_stembiljetten",
        "geen verklaring": "geen_verklaring",
        "andere verklaring": "andere_verklaring",
    }
    rejected_map = {
        "ongeldig": "ongeldig",
        "blanco": "blanco",
    }

    data = {}
    cast_el = votes_el.find("eml:Cast", ns)
    data["cast"] = _int(cast_el)

    counted_el = votes_el.find("eml:TotalCounted", ns)
    data["getelde_stembiljetten"] = _int(counted_el)

    for uv in votes_el.findall("eml:UncountedVotes", ns):
        reason = uv.get("ReasonCode", "")
        col = reason_map.get(reason)
        if col:
            data[col] = _int(uv)

    for rv in votes_el.findall("eml:RejectedVotes", ns):
        reason = rv.get("ReasonCode", "")
        col = rejected_map.get(reason)
        if col:
            data[col] = _int(rv)

    return data


def _parse_stemmen(votes_el, ns: dict) -> tuple[dict[str, int], dict[str, int]]:
    """Parse stemmen per partij en per kandidaat uit een stemmenblok.

    Returns:
        (partij_stemmen {partij_nr: stemmen}, kandidaat_stemmen {partij_nr_volgnr: stemmen})
        Bij Totaaltelling (CSB) hebben kandidaten ShortCode i.p.v. Id;
        dan wordt de key "partij_nr_sc:ShortCode".
    """
    partij_stemmen = {}
    kandidaat_stemmen = {}
    current_partij_nr = None

    for sel in votes_el.findall("eml:Selection", ns):
        aff = sel.find("eml:AffiliationIdentifier", ns)
        cand = sel.find("eml:Candidate", ns)
        votes = _int(sel.find("eml:ValidVotes", ns))

        if aff is not None:
            current_partij_nr = aff.get("Id")
            partij_stemmen[current_partij_nr] = votes
        elif cand is not None and current_partij_nr is not None:
            cid = cand.find("eml:CandidateIdentifier", ns)
            volgnr = cid.get("Id")
            if volgnr is not None:
                key = f"{current_partij_nr}_{volgnr}"
            else:
                # Totaaltelling: ShortCode i.p.v. Id
                shortcode = cid.get("ShortCode", "")
                key = f"{current_partij_nr}_sc:{shortcode}"
            kandidaat_stemmen[key] = votes

    return partij_stemmen, kandidaat_stemmen


def parse_gemeente_tellingen(
    zips: list[zipfile.ZipFile],
    conn: sqlite3.Connection,
    verkiezing_id: int,
    partij_map: dict[str, int],
):
    """Parse alle Gemeente tellingen → gemeenten, stembureaus, stemmen."""
    files = _open_xml_from_zips(zips, "Telling_TK")
    # Filter op gemeente tellingen (niet kieskring)
    gemeente_files = [(n, r) for n, r in files if "gemeente" in n.lower()]
    if not gemeente_files:
        raise FileNotFoundError("Geen gemeente tellingen gevonden")

    # Bouw kandidaat lookup: (partij_id, volgnr) -> kandidaat_id
    kandidaat_lookup = {}
    rows = conn.execute(
        "SELECT id, partij_id, volgnr FROM kandidaten WHERE verkiezing_id=?",
        (verkiezing_id,),
    ).fetchall()
    for kid, pid, vnr in rows:
        kandidaat_lookup[(pid, vnr)] = kid

    gemeente_count = 0
    stembureau_count = 0
    stemmen_partij_rows = []
    stemmen_kandidaat_rows = []

    for filename, root in gemeente_files:
        # Gemeente info
        auth = root.find(".//eml:ManagingAuthority/eml:AuthorityIdentifier", NS)
        gemeente_code = auth.get("Id")
        gemeente_naam = _text(auth)

        # Kieskring info
        contest = root.find(".//eml:Count/eml:Election/eml:Contests/eml:Contest", NS)
        contest_id_el = contest.find("eml:ContestIdentifier", NS)
        kieskring_id = contest_id_el.get("Id")
        kieskring_naam = _text(contest_id_el.find("eml:ContestName", NS))

        # Kiesgerechtigden = Cast op gemeente-niveau (eerste TotalVotes)
        total_votes = contest.find(".//eml:TotalVotes", NS)
        cast_el = total_votes.find("eml:Cast", NS) if total_votes is not None else None
        kiesgerechtigden = _int(cast_el)

        conn.execute(
            "INSERT OR IGNORE INTO gemeenten (verkiezing_id, gemeente_code, naam, kieskring_id, kieskring_naam, kiesgerechtigden) VALUES (?,?,?,?,?,?)",
            (verkiezing_id, gemeente_code, gemeente_naam, kieskring_id, kieskring_naam, kiesgerechtigden),
        )
        gemeente_row = conn.execute(
            "SELECT id FROM gemeenten WHERE verkiezing_id=? AND gemeente_code=?",
            (verkiezing_id, gemeente_code),
        ).fetchone()
        gemeente_id = gemeente_row[0]
        gemeente_count += 1

        # Stembureaus (ReportingUnitVotes)
        for ruv in contest.findall(".//eml:ReportingUnitVotes", NS):
            ru_id_el = ruv.find("eml:ReportingUnitIdentifier", NS)
            sb_code = ru_id_el.get("Id")
            sb_raw_name = _text(ru_id_el)

            # Parse naam en postcode uit "Stembureau Naam (postcode: 1234 AB)"
            postcode = ""
            sb_naam = sb_raw_name
            pc_match = re.search(r"\(postcode:\s*(\d{4}\s*[A-Z]{2})\)", sb_raw_name)
            if pc_match:
                postcode = pc_match.group(1).strip()
                sb_naam = sb_raw_name[: pc_match.start()].strip()

            # Parse teldata
            teldata = _parse_uncounted(ruv, NS)

            conn.execute(
                """INSERT OR IGNORE INTO stembureaus
                   (gemeente_id, stembureau_code, naam, postcode,
                    uitgebrachte_stemmen, toegelaten_kiezers, getelde_stembiljetten,
                    blanco, ongeldig,
                    geldige_stempassen, geldige_volmachtbewijzen, geldige_kiezerspassen,
                    meer_geteld, minder_geteld,
                    meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
                    te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    gemeente_id, sb_code, sb_naam, postcode,
                    teldata.get("cast", 0),
                    teldata.get("toegelaten_kiezers", 0),
                    teldata.get("getelde_stembiljetten", 0),
                    teldata.get("blanco", 0),
                    teldata.get("ongeldig", 0),
                    teldata.get("geldige_stempassen", 0),
                    teldata.get("geldige_volmachtbewijzen", 0),
                    teldata.get("geldige_kiezerspassen", 0),
                    teldata.get("meer_geteld", 0),
                    teldata.get("minder_geteld", 0),
                    teldata.get("meegenomen_stembiljetten", 0),
                    teldata.get("te_weinig_uitgereikte_stembiljetten", 0),
                    teldata.get("te_veel_uitgereikte_stembiljetten", 0),
                    teldata.get("geen_verklaring", 0),
                    teldata.get("andere_verklaring", 0),
                ),
            )
            sb_row = conn.execute(
                "SELECT id FROM stembureaus WHERE gemeente_id=? AND stembureau_code=?",
                (gemeente_id, sb_code),
            ).fetchone()
            sb_id = sb_row[0]
            stembureau_count += 1

            # Stemmen per partij en per kandidaat
            partij_stemmen, kandidaat_stemmen = _parse_stemmen(ruv, NS)

            for pnr, votes in partij_stemmen.items():
                pid = partij_map.get(pnr)
                if pid:
                    stemmen_partij_rows.append((sb_id, pid, votes))

            for key, votes in kandidaat_stemmen.items():
                pnr, vnr = key.split("_")
                pid = partij_map.get(pnr)
                if pid:
                    kid = kandidaat_lookup.get((pid, int(vnr)))
                    if kid:
                        stemmen_kandidaat_rows.append((sb_id, kid, votes))

    # Bulk insert stemmen
    conn.executemany(
        "INSERT OR IGNORE INTO stemmen_partij (stembureau_id, partij_id, stemmen) VALUES (?,?,?)",
        stemmen_partij_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO stemmen_kandidaat (stembureau_id, kandidaat_id, stemmen) VALUES (?,?,?)",
        stemmen_kandidaat_rows,
    )
    conn.commit()

    print(f"  Gemeenten: {gemeente_count}")
    print(f"  Stembureaus: {stembureau_count}")
    print(f"  Stemmen partij rijen: {len(stemmen_partij_rows)}")
    print(f"  Stemmen kandidaat rijen: {len(stemmen_kandidaat_rows)}")


def parse_kieskring_tellingen(
    zips: list[zipfile.ZipFile],
    conn: sqlite3.Connection,
    verkiezing_id: int,
    partij_map: dict[str, int],
):
    """Parse kieskring tellingen (HSB-niveau) → kieskringen + stemmen."""
    files = _open_xml_from_zips(zips, "Telling_TK")
    kieskring_files = [(n, r) for n, r in files if "kieskring" in n.lower()]
    if not kieskring_files:
        print("  Waarschuwing: geen kieskring tellingen gevonden, wordt overgeslagen")
        return

    # Bouw kandidaat lookup
    kandidaat_lookup = {}
    rows = conn.execute(
        "SELECT id, partij_id, volgnr FROM kandidaten WHERE verkiezing_id=?",
        (verkiezing_id,),
    ).fetchall()
    for kid, pid, vnr in rows:
        kandidaat_lookup[(pid, vnr)] = kid

    kieskring_count = 0
    stemmen_partij_rows = []
    stemmen_kandidaat_rows = []

    for filename, root in kieskring_files:
        # Kieskring info uit ManagingAuthority
        auth = root.find(".//eml:ManagingAuthority/eml:AuthorityIdentifier", NS)
        kieskring_code = auth.get("Id")  # bijv. "HSB9"
        kieskring_naam = _text(auth)     # bijv. "Amsterdam"

        # Contest info (TotalVotes = kieskring totaal)
        contest = root.find(".//eml:Count/eml:Election/eml:Contests/eml:Contest", NS)
        total_votes = contest.find("eml:TotalVotes", NS)

        # Parse teldata
        teldata = _parse_uncounted(total_votes, NS)

        conn.execute(
            """INSERT OR IGNORE INTO kieskringen
               (verkiezing_id, kieskring_code, naam,
                kiesgerechtigden, getelde_stembiljetten, blanco, ongeldig,
                geldige_volmachtbewijzen, geldige_kiezerspassen,
                meer_geteld, minder_geteld,
                meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
                te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                verkiezing_id, kieskring_code, kieskring_naam,
                teldata.get("cast", 0),
                teldata.get("getelde_stembiljetten", 0),
                teldata.get("blanco", 0),
                teldata.get("ongeldig", 0),
                teldata.get("geldige_volmachtbewijzen", 0),
                teldata.get("geldige_kiezerspassen", 0),
                teldata.get("meer_geteld", 0),
                teldata.get("minder_geteld", 0),
                teldata.get("meegenomen_stembiljetten", 0),
                teldata.get("te_weinig_uitgereikte_stembiljetten", 0),
                teldata.get("te_veel_uitgereikte_stembiljetten", 0),
                teldata.get("geen_verklaring", 0),
                teldata.get("andere_verklaring", 0),
            ),
        )
        kk_row = conn.execute(
            "SELECT id FROM kieskringen WHERE verkiezing_id=? AND kieskring_code=?",
            (verkiezing_id, kieskring_code),
        ).fetchone()
        kk_id = kk_row[0]
        kieskring_count += 1

        # Stemmen per partij en per kandidaat uit TotalVotes
        partij_stemmen, kandidaat_stemmen = _parse_stemmen(total_votes, NS)

        for pnr, votes in partij_stemmen.items():
            pid = partij_map.get(pnr)
            if pid:
                stemmen_partij_rows.append((kk_id, pid, votes))

        for key, votes in kandidaat_stemmen.items():
            pnr, vnr = key.split("_")
            pid = partij_map.get(pnr)
            if pid:
                kid = kandidaat_lookup.get((pid, int(vnr)))
                if kid:
                    stemmen_kandidaat_rows.append((kk_id, kid, votes))

    # Bulk insert
    conn.executemany(
        "INSERT OR IGNORE INTO kieskring_stemmen_partij (kieskring_id, partij_id, stemmen) VALUES (?,?,?)",
        stemmen_partij_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO kieskring_stemmen_kandidaat (kieskring_id, kandidaat_id, stemmen) VALUES (?,?,?)",
        stemmen_kandidaat_rows,
    )
    conn.commit()

    print(f"  Kieskringen: {kieskring_count}")
    print(f"  Stemmen partij rijen: {len(stemmen_partij_rows)}")
    print(f"  Stemmen kandidaat rijen: {len(stemmen_kandidaat_rows)}")


def parse_totaaltelling(
    zips: list[zipfile.ZipFile],
    conn: sqlite3.Connection,
    verkiezing_id: int,
    partij_map: dict[str, int],
):
    """Parse Totaaltelling (CSB-niveau) → csb_totalen + stemmen."""
    files = _open_xml_from_zips(zips, "Totaaltelling")
    if not files:
        print("  Waarschuwing: geen Totaaltelling gevonden, wordt overgeslagen")
        return

    _, root = files[0]

    # Bouw kandidaat lookups: zowel (partij_id, volgnr) als ShortCode
    kandidaat_by_volgnr = {}
    shortcode_lookup = {}  # (partij_id, shortcode) -> kandidaat_id
    rows = conn.execute(
        "SELECT id, partij_id, volgnr, naam, initialen, tussenvoegsel FROM kandidaten WHERE verkiezing_id=?",
        (verkiezing_id,),
    ).fetchall()
    for kid, pid, vnr, naam, initialen, tussenvoegsel in rows:
        kandidaat_by_volgnr[(pid, vnr)] = kid
        # Bouw ShortCode: achternaam + initialen zonder punten/spaties
        # Voorbeeld: "Wilders" + "G." -> "WildersG"
        clean_initialen = (initialen or "").replace(".", "").replace(" ", "")
        clean_naam = (naam or "").replace(" ", "")
        if tussenvoegsel:
            # bijv. "van Dijk" -> "DijkE" (tussenvoegsel in ShortCode is achternaam-deel)
            sc = f"{clean_naam}{clean_initialen}"
        else:
            sc = f"{clean_naam}{clean_initialen}"
        shortcode_lookup[(pid, sc)] = kid

    contest = root.find(".//eml:Count/eml:Election/eml:Contests/eml:Contest", NS)
    total_votes = contest.find("eml:TotalVotes", NS)

    # Parse teldata
    teldata = _parse_uncounted(total_votes, NS)

    conn.execute(
        """INSERT OR IGNORE INTO csb_totalen
           (verkiezing_id,
            kiesgerechtigden, getelde_stembiljetten, blanco, ongeldig,
            geldige_volmachtbewijzen, geldige_kiezerspassen,
            meer_geteld, minder_geteld,
            meegenomen_stembiljetten, te_weinig_uitgereikte_stembiljetten,
            te_veel_uitgereikte_stembiljetten, geen_verklaring, andere_verklaring)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            verkiezing_id,
            teldata.get("cast", 0),
            teldata.get("getelde_stembiljetten", 0),
            teldata.get("blanco", 0),
            teldata.get("ongeldig", 0),
            teldata.get("geldige_volmachtbewijzen", 0),
            teldata.get("geldige_kiezerspassen", 0),
            teldata.get("meer_geteld", 0),
            teldata.get("minder_geteld", 0),
            teldata.get("meegenomen_stembiljetten", 0),
            teldata.get("te_weinig_uitgereikte_stembiljetten", 0),
            teldata.get("te_veel_uitgereikte_stembiljetten", 0),
            teldata.get("geen_verklaring", 0),
            teldata.get("andere_verklaring", 0),
        ),
    )

    # Stemmen per partij en per kandidaat
    partij_stemmen, kandidaat_stemmen = _parse_stemmen(total_votes, NS)

    csb_partij_rows = []
    csb_kandidaat_rows = []
    unmatched = 0

    for pnr, votes in partij_stemmen.items():
        pid = partij_map.get(pnr)
        if pid:
            csb_partij_rows.append((verkiezing_id, pid, votes))

    for key, votes in kandidaat_stemmen.items():
        pnr, rest = key.split("_", 1)
        pid = partij_map.get(pnr)
        if pid:
            if rest.startswith("sc:"):
                # ShortCode-gebaseerde key
                sc = rest[3:]
                kid = shortcode_lookup.get((pid, sc))
            else:
                kid = kandidaat_by_volgnr.get((pid, int(rest)))
            if kid:
                csb_kandidaat_rows.append((verkiezing_id, kid, votes))
            else:
                unmatched += 1

    if unmatched:
        print(f"  Waarschuwing: {unmatched} CSB-kandidaatstemmen niet gematcht")

    conn.executemany(
        "INSERT OR IGNORE INTO csb_stemmen_partij (verkiezing_id, partij_id, stemmen) VALUES (?,?,?)",
        csb_partij_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO csb_stemmen_kandidaat (verkiezing_id, kandidaat_id, stemmen) VALUES (?,?,?)",
        csb_kandidaat_rows,
    )
    conn.commit()

    print(f"  CSB totalen: 1 rij")
    print(f"  Stemmen partij rijen: {len(csb_partij_rows)}")
    print(f"  Stemmen kandidaat rijen: {len(csb_kandidaat_rows)}")


def parse_resultaat(
    zips: list[zipfile.ZipFile],
    conn: sqlite3.Connection,
    verkiezing_id: int,
    partij_map: dict[str, int],
):
    """Parse Resultaat → zetels + gekozen_kandidaten."""
    files = _open_xml_from_zips(zips, "Resultaat")
    if not files:
        print("  Waarschuwing: geen Resultaat gevonden, zetels/gekozen worden overgeslagen")
        return

    _, root = files[0]
    contest = root.find(".//eml:Result/eml:Election/eml:Contest", NS)

    # Bouw kandidaat lookup
    kandidaat_lookup = {}
    rows = conn.execute(
        "SELECT id, partij_id, volgnr FROM kandidaten WHERE verkiezing_id=?",
        (verkiezing_id,),
    ).fetchall()
    for kid, pid, vnr in rows:
        kandidaat_lookup[(pid, vnr)] = kid

    current_partij_nr = None
    zetels_per_partij = {}
    gekozen_rows = []

    for sel in contest.findall("eml:Selection", NS):
        aff = sel.find("eml:AffiliationIdentifier", NS)
        cand = sel.find("eml:Candidate", NS)

        if aff is not None:
            current_partij_nr = aff.get("Id")
            if current_partij_nr not in zetels_per_partij:
                zetels_per_partij[current_partij_nr] = 0
        elif cand is not None and current_partij_nr is not None:
            elected = sel.find("eml:Elected", NS)
            ranking = sel.find("eml:Ranking", NS)

            if elected is not None and _text(elected) == "yes":
                zetels_per_partij[current_partij_nr] = zetels_per_partij.get(current_partij_nr, 0) + 1

                cid = cand.find("eml:CandidateIdentifier", NS)
                volgnr = int(cid.get("Id"))
                pid = partij_map.get(current_partij_nr)
                if pid:
                    kid = kandidaat_lookup.get((pid, volgnr))
                    rank_val = _int(ranking) if ranking is not None else None
                    if kid:
                        gekozen_rows.append((verkiezing_id, pid, kid, rank_val))

    # Insert zetels per partij
    for pnr, zetels in zetels_per_partij.items():
        if zetels > 0:
            pid = partij_map.get(pnr)
            if pid:
                conn.execute(
                    "INSERT OR IGNORE INTO zetels (verkiezing_id, partij_id, zetels) VALUES (?,?,?)",
                    (verkiezing_id, pid, zetels),
                )

    conn.executemany(
        "INSERT OR IGNORE INTO gekozen_kandidaten (verkiezing_id, partij_id, kandidaat_id, ranking) VALUES (?,?,?,?)",
        gekozen_rows,
    )
    conn.commit()

    print(f"  Zetels verdeeld over {len([z for z in zetels_per_partij.values() if z > 0])} partijen")
    print(f"  Gekozen kandidaten: {len(gekozen_rows)}")


# ---------------------------------------------------------------------------
# Hoofdfunctie
# ---------------------------------------------------------------------------

def build_database(eml_dir: Path = EML_DIR, db_path: Path = DB_PATH):
    """Bouw de volledige SQLite database vanuit EML zip-bestanden."""
    print(f"EML-bestanden: {eml_dir}")
    print(f"Database: {db_path}")

    zips_paths = _find_zips(eml_dir)
    zips = [zipfile.ZipFile(str(p)) for p in zips_paths]
    print(f"Gevonden zip-bestanden: {len(zips)}")

    conn = _create_db(db_path)

    try:
        print("\n1. Verkiezingsdefinitie parsen...")
        verkiezing_id = parse_verkiezingsdefinitie(zips, conn)

        print("\n2. Kandidatenlijsten parsen...")
        partij_map = parse_kandidatenlijsten(zips, conn, verkiezing_id)

        print("\n3. Gemeente tellingen parsen...")
        parse_gemeente_tellingen(zips, conn, verkiezing_id, partij_map)

        print("\n3b. Kieskring tellingen parsen (HSB-niveau)...")
        parse_kieskring_tellingen(zips, conn, verkiezing_id, partij_map)

        print("\n3c. Totaaltelling parsen (CSB-niveau)...")
        parse_totaaltelling(zips, conn, verkiezing_id, partij_map)

        print("\n4. Resultaat parsen (zetels + gekozen kandidaten)...")
        parse_resultaat(zips, conn, verkiezing_id, partij_map)

        print("\n5. Views en indexes aanmaken...")
        conn.executescript(VIEWS)
        conn.executescript(INDEXES)
        conn.commit()

        # Verificatie
        print("\n=== Verificatie ===")
        for table in ["verkiezingen", "partijen", "kandidaten", "gemeenten", "stembureaus",
                       "stemmen_partij", "stemmen_kandidaat", "zetels", "gekozen_kandidaten",
                       "kieskringen", "kieskring_stemmen_partij", "kieskring_stemmen_kandidaat",
                       "csb_totalen", "csb_stemmen_partij", "csb_stemmen_kandidaat"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rijen")

        # Quick check: totaal stemmen PVV
        row = conn.execute("""
            SELECT p.naam_kort, SUM(sp.stemmen)
            FROM stemmen_partij sp
            JOIN partijen p ON p.id = sp.partij_id
            WHERE p.naam_kort = 'PVV'
        """).fetchone()
        if row:
            print(f"\n  Check: {row[0]} totaal = {row[1]} stemmen")

    finally:
        for z in zips:
            z.close()
        conn.close()

    print(f"\nDatabase succesvol gebouwd: {db_path}")
    print(f"Grootte: {db_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    build_database()

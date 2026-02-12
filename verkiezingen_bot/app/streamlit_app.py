"""
Streamlit chat-interface voor de Verkiezingen Chatbot.
Design gebaseerd op de Kiesraad Toolkit Verkiezingen huisstijl.
"""

import base64
import os
import sys
import time
from pathlib import Path

# Zorg dat de repo-root in het Python-pad staat (nodig voor Streamlit Cloud)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

# Maak secrets beschikbaar als environment variables (voor Streamlit Cloud)
try:
    if "OPENROUTER_API_KEY" in st.secrets:
        os.environ["OPENROUTER_API_KEY"] = st.secrets["OPENROUTER_API_KEY"]
except FileNotFoundError:
    pass

from verkiezingen_bot.app.feedback import save_feedback
from verkiezingen_bot.app.qa import QAEngine

# Pagina-instellingen
st.set_page_config(
    page_title="Kiki – Verkiezingen Chatbot GR26",
    page_icon="🗳️",
    layout="centered",
)


def svg_to_data_uri(svg: str) -> str:
    """Zet een SVG-string om naar een data URI voor gebruik als avatar."""
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


# === AVATAR SVGs ===

# Rood potlood avatar voor assistent (blauwe zeshoek-achtergrond)
PENCIL_AVATAR_SVG = (
    '<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
    '<polygon points="50,3 93,28 93,72 50,97 7,72 7,28" fill="#002f5b" stroke="#002f5b" stroke-width="2"/>'
    '<g transform="translate(50,48) rotate(-45)">'
    '<rect x="-7" y="-28" width="14" height="38" rx="1" fill="#cc0000"/>'
    '<polygon points="-7,10 0,22 7,10" fill="#f0c878"/>'
    '<polygon points="-3,16 0,22 3,16" fill="#333"/>'
    '<rect x="-7" y="-28" width="14" height="5" rx="1" fill="#c0c0c0"/>'
    '<line x1="-3" y1="-25" x2="-3" y2="10" stroke="#e64040" stroke-width="2" opacity="0.5"/>'
    '</g>'
    '</svg>'
)

# Gebruiker avatar: zeshoek met persoon-silhouet in Kiesraad blauw
USER_AVATAR_SVG = (
    '<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
    '<polygon points="50,3 93,28 93,72 50,97 7,72 7,28" fill="#002f5b"/>'
    '<circle cx="50" cy="36" r="14" fill="white"/>'
    '<ellipse cx="50" cy="76" rx="22" ry="17" fill="white"/>'
    '</svg>'
)

ASSISTANT_AVATAR = svg_to_data_uri(PENCIL_AVATAR_SVG)
USER_AVATAR = svg_to_data_uri(USER_AVATAR_SVG)


# === KIESRAAD HUISSTIJL ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:ital,wght@0,400;0,500;0,700;1,400&display=swap');

    /* Verberg Streamlit standaard UI elementen */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Basis */
    .stApp {
        background-color: #ffffff;
    }

    /* Alle tekst in DM Sans — brede override */
    .stApp,
    .stApp p, .stApp li, .stApp span, .stApp div, .stApp td, .stApp th,
    .stApp label, .stApp input, .stApp textarea, .stApp button,
    .stApp [class*="markdown"],
    .stApp [data-testid="stChatMessage"],
    .stApp [data-testid="stChatMessage"] p,
    .stApp [data-testid="stChatMessage"] li,
    .stApp [data-testid="stChatMessage"] strong,
    .stApp [data-testid="stChatMessage"] em,
    .stApp [data-testid="stChatInput"] textarea {
        font-family: 'DM Sans', sans-serif !important;
    }

    /* Koppen in Space Grotesk */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    .kiki-header h1,
    .source-box .source-title,
    .welcome-card h3 {
        font-family: 'Space Grotesk', sans-serif !important;
    }

    /* Header balk */
    .kiki-header {
        background-color: #002f5b;
        margin: -6rem -4rem 1.5rem -4rem;
        padding: 1.8rem 2rem 1.5rem 2rem;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .kiki-header::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #e3032d 0%, #ee8050 50%, #f8ccb8 100%);
    }

    /* Hexagonale icoon-container */
    .hex-icon {
        display: inline-block;
        vertical-align: middle;
        margin-right: 8px;
        margin-bottom: 4px;
    }

    /* Chat berichten */
    [data-testid="stChatMessage"] {
        border-radius: 8px;
        margin-bottom: 0.5rem;
    }

    /* Avatar styling — verwijder vierkante rand rond SVG avatars */
    [data-testid="stChatMessage"] [data-testid="stAvatar"],
    [data-testid="stChatMessage"] [data-testid="stAvatar"] > div {
        background: transparent !important;
        border: none !important;
    }

    /* Chat input */
    [data-testid="stChatInput"] textarea {
        border-radius: 8px;
        border: 2px solid #002f5b;
    }
    [data-testid="stChatInput"] textarea:focus {
        border-color: #e3032d;
    }

    /* Bronnen box */
    .source-box {
        background-color: #efefef;
        border-left: 4px solid #ee8050;
        padding: 0.8rem 1rem;
        margin-top: 0.8rem;
        border-radius: 0 6px 6px 0;
        font-size: 0.85rem;
    }
    .source-box .source-title {
        font-weight: 600;
        color: #002f5b;
        font-size: 0.85rem;
        margin-bottom: 0.3rem;
    }
    .source-box a {
        color: #002f5b;
        text-decoration: none;
        font-weight: 500;
    }
    .source-box a:hover {
        color: #e3032d;
        text-decoration: underline;
    }
    .source-box ul {
        margin: 0.3rem 0 0 0;
        padding-left: 1.2rem;
    }
    .source-box li {
        margin-bottom: 0.2rem;
        color: #333;
    }

    /* Responstijd badge */
    .response-time {
        display: inline-block;
        background-color: #002f5b;
        color: #f8ccb8;
        font-size: 0.72rem;
        padding: 2px 10px;
        border-radius: 10px;
        margin-top: 0.5rem;
        font-weight: 500;
    }

    /* Welkomstblok */
    .welcome-card {
        background: #efefef;
        border-radius: 10px;
        padding: 1.8rem;
        margin-bottom: 1rem;
    }
    .welcome-card h3 {
        color: #002f5b;
        margin-top: 0;
        font-weight: 700;
        font-size: 1.3rem;
    }
    .welcome-card p {
        color: #333;
        margin-bottom: 0.8rem;
        line-height: 1.5;
    }
    .welcome-notice {
        display: flex;
        align-items: flex-start;
        gap: 0.6rem;
        background: white;
        border-radius: 8px;
        padding: 0.7rem 0.9rem;
        margin-top: 0.6rem;
        font-size: 0.84rem;
        color: #444;
        line-height: 1.5;
    }
    .welcome-notice .wn-icon {
        flex-shrink: 0;
        margin-top: 1px;
    }
    .welcome-notice a {
        color: #002f5b;
        font-weight: 500;
    }
    .welcome-notice a:hover {
        color: #e3032d;
    }

    /* === FEEDBACK KNOPPEN === */
    .feedback-container {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.5rem;
    }
    .feedback-thanks {
        font-size: 0.8rem;
        color: #666;
        margin-top: 0.4rem;
    }

    /* === DENKANIMATIE === */
    .thinking-animation {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 0.5rem 0;
        color: #002f5b;
    }
    .thinking-animation .thinking-text {
        font-size: 0.9rem;
    }
    .stemvakjes {
        display: inline-flex;
        gap: 8px;
    }

    /* === HEADER STEMBILJET === */
    .header-ballot {
        display: inline-flex;
        background: #f9f6f0;
        border: 2px solid #c0b8a8;
        border-radius: 3px;
        box-shadow: 3px 4px 14px rgba(0,0,0,0.22);
        overflow: hidden;
    }
    .hb-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        color: #002f5b;
        text-align: center;
        letter-spacing: 0.14em;
        padding: 12px 24px 8px 24px;
        border-bottom: 2px solid #002f5b;
    }
    .hb-body {
        display: flex;
    }
    /* Elke kolom is een vouwpaneel */
    .hb-col {
        padding: 10px 20px 14px 20px;
        min-width: 80px;
    }
    .hb-col:not(:last-child) {
        border-right: 1px solid #d0c8b8;
    }
    /* Kolom 1: vouwt open vanuit links */
    .hb-col-1 {
        transform-origin: left center;
        transform: perspective(600px) rotateY(-90deg);
        animation: unfoldCol 0.6s ease-out 0.3s forwards;
    }
    /* Kolom 2: vouwt open vanuit links */
    .hb-col-2 {
        transform-origin: left center;
        transform: perspective(600px) rotateY(-90deg);
        animation: unfoldCol 0.6s ease-out 1.1s forwards;
    }
    /* Kolom 3: vouwt open vanuit links */
    .hb-col-3 {
        transform-origin: left center;
        transform: perspective(600px) rotateY(-90deg);
        animation: unfoldCol 0.6s ease-out 1.9s forwards;
    }
    @keyframes unfoldCol {
        0%   { transform: perspective(600px) rotateY(-90deg); }
        100% { transform: perspective(600px) rotateY(0deg); }
    }
    .hb-party {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.8rem;
        font-weight: 700;
        color: #002f5b;
        margin-bottom: 7px;
    }
    .hb-row {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 5px;
    }
    .hb-c {
        width: 14px; height: 14px;
        border-radius: 50%;
        border: 1.5px solid #555;
        background: white;
        flex-shrink: 0;
        position: relative;
    }
    .hb-c.voted::after {
        content: '';
        position: absolute;
        top: 2px; left: 2px;
        width: 8px; height: 8px;
        border-radius: 50%;
        background: #e3032d;
        transform: scale(0);
        animation: hbVote 0.3s ease-out 2.8s forwards;
    }
    @keyframes hbVote {
        from { transform: scale(0); }
        to { transform: scale(1); }
    }
    .hb-line {
        height: 2px;
        width: 42px;
        background: #c0b8a8;
        border-radius: 1px;
    }

</style>
""", unsafe_allow_html=True)


def hex_icon(icon_type="pencil", size=44):
    """Genereer een zeshoekig icoon in Kiesraad-stijl."""
    if icon_type == "pencil":
        # Nederlands rood potlood in zeshoekig kader (blauwe achtergrond)
        return (
            f'<svg class="hex-icon" width="{size}" height="{size}" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<polygon points="50,3 93,28 93,72 50,97 7,72 7,28" fill="none" stroke="none"/>'
            '<g transform="translate(50,48) rotate(-45)">'
            # Potloodlichaam — dik en rood, zoals het Nederlandse stempotlood
            '<rect x="-6" y="-26" width="12" height="36" rx="1" fill="#cc0000"/>'
            # Houtkleurige punt
            '<polygon points="-6,10 0,20 6,10" fill="#f0c878"/>'
            # Grafietpunt
            '<polygon points="-2,16 0,21 2,16" fill="#333"/>'
            # Metalen ring bovenaan
            '<rect x="-6" y="-26" width="12" height="4" rx="1" fill="#c0c0c0"/>'
            # Lichtstreep op potlood
            '<line x1="-3" y1="-24" x2="-3" y2="10" stroke="#e64040" stroke-width="2" opacity="0.6"/>'
            '</g>'
            '</svg>'
        )
    elif icon_type == "ballot":
        # Stembiljet met stemvakjes — Nederlands verkiezingsthema
        return (
            f'<svg class="hex-icon" width="{size}" height="{size}" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<polygon points="50,3 93,28 93,72 50,97 7,72 7,28" fill="#ee8050" stroke="#002f5b" stroke-width="2"/>'
            # Stembiljet (wit papier)
            '<rect x="28" y="20" width="44" height="60" rx="2" fill="white"/>'
            # Vakje 1: leeg stemrondje met naam
            '<circle cx="37" cy="34" r="5" fill="none" stroke="#002f5b" stroke-width="1.5"/>'
            '<line x1="47" y1="34" x2="65" y2="34" stroke="#ccc" stroke-width="2"/>'
            # Vakje 2: ingevuld stemrondje (gestemd!) met naam
            '<circle cx="37" cy="48" r="5" fill="white" stroke="#002f5b" stroke-width="1.5"/>'
            '<line x1="32" y1="43" x2="42" y2="53" stroke="#e3032d" stroke-width="2.5" stroke-linecap="round"/>'
            '<line x1="34" y1="51" x2="40" y2="45" stroke="#e3032d" stroke-width="2.5" stroke-linecap="round"/>'
            '<line x1="47" y1="48" x2="65" y2="48" stroke="#ccc" stroke-width="2"/>'
            # Vakje 3: leeg stemrondje met naam
            '<circle cx="37" cy="62" r="5" fill="none" stroke="#002f5b" stroke-width="1.5"/>'
            '<line x1="47" y1="62" x2="60" y2="62" stroke="#ccc" stroke-width="2"/>'
            '</svg>'
        )
    elif icon_type == "search":
        # Vraagteken in zeshoek
        return (
            f'<svg class="hex-icon" width="20" height="20" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<polygon points="50,3 93,28 93,72 50,97 7,72 7,28" fill="#e3032d"/>'
            '<text x="50" y="64" text-anchor="middle" fill="white" font-size="50" font-weight="bold"'
            ' font-family="Space Grotesk, sans-serif">?</text>'
            '</svg>'
        )
    elif icon_type == "source":
        # Document icoon in zeshoek
        return (
            f'<svg class="hex-icon" width="18" height="18" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
            '<polygon points="50,5 90,28 90,72 50,95 10,72 10,28" fill="#ee8050"/>'
            '<rect x="30" y="25" width="40" height="50" rx="2" fill="white"/>'
            '<line x1="36" y1="38" x2="64" y2="38" stroke="#002f5b" stroke-width="3"/>'
            '<line x1="36" y1="48" x2="64" y2="48" stroke="#002f5b" stroke-width="3"/>'
            '<line x1="36" y1="58" x2="55" y2="58" stroke="#002f5b" stroke-width="3"/>'
            '</svg>'
        )
    return ""


def _stemvakje_svg(vakje_idx: int) -> str:
    """
    Eén stemvakje voor de denkanimatie: zwart vierkant, wit rondje erin.
    Drie diagonale potloodkrassen kleuren het rood in (rechts→links, gespiegeld).
    Alle vakjes delen dezelfde tijdlijn (5s cyclus).
    """
    dur = 5.0

    # Wanneer dit vakje begint met inkleuren
    draw_start = 0.2 + vakje_idx * 0.9
    scratch_offsets = [0, 0.15, 0.30]
    scratch_draw_time = 0.30

    hold_end = 3.5
    erase_end = 3.8

    # Gespiegelde diagonale krassen: rechts→links (x1/x2 omgedraaid)
    scratches = [
        (84, 16, 16, 84, 96.2),   # rechts-boven → links-onder
        (90, 44, 20, 94, 86.0),   # rechts-midden → links-onder
        (80, 6, 10, 56, 86.0),    # rechts-boven → links-midden
    ]

    lines_svg = ""
    for i, (x1, y1, x2, y2, length) in enumerate(scratches):
        s_start = draw_start + scratch_offsets[i]
        s_end = s_start + scratch_draw_time

        t1 = round(s_start / dur, 4)
        t2 = round(s_end / dur, 4)
        t3 = round(hold_end / dur, 4)
        t4 = round(erase_end / dur, 4)

        key_times = f"0;{t1};{t2};{t3};{t4};1"
        dash_values = f"{length};{length};0;0;{length};{length}"
        # Opacity: onzichtbaar tot tekenen begint, dan zichtbaar, dan weer weg
        opacity_values = f"0;0;1;1;0;0"
        splines = "0 0 1 1; 0.2 0 0.6 1; 0 0 1 1; 0.4 0 0.8 1; 0 0 1 1"

        lines_svg += (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#e3032d" stroke-width="17" stroke-linecap="round" '
            f'stroke-dasharray="{length}" stroke-dashoffset="{length}" stroke-opacity="0">'
            f'<animate attributeName="stroke-dashoffset" '
            f'values="{dash_values}" keyTimes="{key_times}" '
            f'dur="{dur}s" repeatCount="indefinite" '
            f'calcMode="spline" keySplines="{splines}"/>'
            f'<animate attributeName="stroke-opacity" '
            f'values="{opacity_values}" keyTimes="{key_times}" '
            f'dur="{dur}s" repeatCount="indefinite" '
            f'calcMode="spline" keySplines="{splines}"/>'
            f'</line>'
        )

    return (
        f'<svg width="30" height="30" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><clipPath id="sv{vakje_idx}">'
        f'<circle cx="50" cy="50" r="46"/>'
        f'</clipPath></defs>'
        f'<rect x="2" y="2" width="96" height="96" rx="4" fill="#1a1a1a"/>'
        f'<circle cx="50" cy="50" r="42" fill="white"/>'
        f'<g clip-path="url(#sv{vakje_idx})">{lines_svg}</g>'
        f'</svg>'
    )


THINKING_HTML = (
    '<div class="thinking-animation">'
    '<div class="stemvakjes">'
    + _stemvakje_svg(0) + _stemvakje_svg(1) + _stemvakje_svg(2)
    + '</div>'
    '<span class="thinking-text">Even denken...</span>'
    '</div>'
)

# Header met stembiljet
st.markdown("""
<div class="kiki-header">
    <div class="header-ballot">
        <div class="hb-title">CHATBOT KIKI</div>
        <div class="hb-body">
            <div class="hb-col hb-col-1">
                <div class="hb-party">Correct</div>
                <div class="hb-row"><span class="hb-c voted"></span><span class="hb-line"></span></div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
            </div>
            <div class="hb-col hb-col-2">
                <div class="hb-party">Fout</div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
            </div>
            <div class="hb-col hb-col-3">
                <div class="hb-party">Verzonnen</div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
                <div class="hb-row"><span class="hb-c"></span><span class="hb-line"></span></div>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


def render_sources(sources: list[dict]):
    """Toon bronverwijzingen onder een antwoord."""
    if not sources:
        return
    html = f'<div class="source-box">'
    html += f'<div class="source-title">{hex_icon("source")} Bronnen</div>'
    html += '<ul>'
    for src in sources:
        titel = src.get("titel", "Onbekend")
        url = src.get("url", "")
        sectie = src.get("sectie", "")
        label = f"{titel} &ndash; {sectie}" if sectie else titel
        if url:
            html += f'<li><a href="{url}" target="_blank">{label}</a></li>'
        else:
            html += f"<li>{label}</li>"
    html += "</ul></div>"
    st.markdown(html, unsafe_allow_html=True)


def render_response_time(seconds: float):
    """Toon hoe lang het antwoord duurde."""
    st.markdown(
        f'<div class="response-time">Antwoord in {seconds:.1f} seconden</div>',
        unsafe_allow_html=True,
    )


@st.cache_resource
def load_engine(_version=2):
    """Laad de QA engine (cached zodat het maar 1x gebeurt)."""
    return QAEngine()


# Laad engine
with st.spinner("Chatbot wordt geladen..."):
    engine = load_engine()

# Chat-geschiedenis en feedback-status
if "messages" not in st.session_state:
    st.session_state.messages = []
if "feedback" not in st.session_state:
    st.session_state.feedback = {}  # {msg_index: "positief" | "negatief"}

# Welkomstblok als er nog geen berichten zijn
if not st.session_state.messages:
    pencil_mini = hex_icon("search")

    notice_icon = hex_icon("search")
    doc_icon = hex_icon("source")
    st.markdown(f"""
    <div class="welcome-card">
        <h3>{hex_icon("ballot", 32)} Welkom bij Kiki!</h3>
        <p>Ik ben Kiki, een chatbot die vragen beantwoordt over de
        <strong>gemeenteraadsverkiezingen 2026</strong>. Mijn kennis is gebaseerd op
        de Toolkit Verkiezingen van de Kiesraad. Stel hieronder een vraag!</p>
        <div class="welcome-notice">
            <span class="wn-icon">{notice_icon}</span>
            <span><strong>Goed om te weten:</strong> Kiki heeft geen geheugen — elke vraag
            wordt los beantwoord. Stel dus elke keer een complete vraag.
            De eerste vraag kan even duren (~30 sec.).</span>
        </div>
        <div class="welcome-notice">
            <span class="wn-icon">{doc_icon}</span>
            <span><strong>Disclaimer:</strong> Kiki is een AI-assistent en kan fouten maken.
            Controleer belangrijke informatie altijd op
            <a href="https://www.kiesraad.nl" target="_blank">kiesraad.nl</a>.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Toon eerdere berichten
for idx, message in enumerate(st.session_state.messages):
    avatar = ASSISTANT_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        if message.get("sources"):
            render_sources(message["sources"])
        if message.get("response_time"):
            render_response_time(message["response_time"])

        # Feedback-knoppen bij assistant-berichten
        if message["role"] == "assistant":
            fb_key = str(idx)
            if fb_key in st.session_state.feedback:
                # Feedback al gegeven — toon bevestiging
                rating = st.session_state.feedback[fb_key]
                icon = "\U0001f44d" if rating == "positief" else "\U0001f44e"
                st.markdown(
                    f'<div class="feedback-thanks">{icon} Bedankt voor je feedback!</div>',
                    unsafe_allow_html=True,
                )
            elif st.session_state.get(f"show_comment_{idx}"):
                # Negatief geklikt, wacht op toelichting
                comment = st.text_input(
                    "Wat klopt er niet? (optioneel)",
                    key=f"comment_{idx}",
                    placeholder="Bijv. het antwoord gaat over het verkeerde model...",
                )
                if st.button("Verstuur feedback", key=f"send_{idx}"):
                    question = ""
                    for prev in range(idx - 1, -1, -1):
                        if st.session_state.messages[prev]["role"] == "user":
                            question = st.session_state.messages[prev]["content"]
                            break
                    save_feedback(question, message["content"], "negatief", comment)
                    st.session_state.feedback[fb_key] = "negatief"
                    del st.session_state[f"show_comment_{idx}"]
                    st.rerun()
            else:
                # Toon duim knoppen + "Meer hierover" knop
                is_last_assistant = idx == len(st.session_state.messages) - 1
                if is_last_assistant and not message.get("is_detailed"):
                    cols = st.columns([1, 1, 2, 4])
                else:
                    cols = st.columns([1, 1, 6])
                with cols[0]:
                    if st.button("\U0001f44d", key=f"pos_{idx}", help="Correct antwoord"):
                        st.session_state.feedback[fb_key] = "positief"
                        question = ""
                        for prev in range(idx - 1, -1, -1):
                            if st.session_state.messages[prev]["role"] == "user":
                                question = st.session_state.messages[prev]["content"]
                                break
                        save_feedback(question, message["content"], "positief")
                        st.rerun()
                with cols[1]:
                    if st.button("\U0001f44e", key=f"neg_{idx}", help="Niet correct"):
                        st.session_state[f"show_comment_{idx}"] = True
                        st.rerun()
                # "Meer hierover" knop — alleen bij het laatste antwoord
                if is_last_assistant and not message.get("is_detailed"):
                    with cols[2]:
                        if st.button("Meer hierover", key=f"detail_{idx}", help="Uitgebreider antwoord"):
                            st.session_state["detail_request"] = idx
                            st.rerun()

# Verwerk "Meer hierover" verzoek
if "detail_request" in st.session_state:
    detail_idx = st.session_state.pop("detail_request")
    # Zoek de oorspronkelijke vraag
    question = ""
    for prev in range(detail_idx - 1, -1, -1):
        if st.session_state.messages[prev]["role"] == "user":
            question = st.session_state.messages[prev]["content"]
            break
    short_answer = st.session_state.messages[detail_idx]["content"]

    if question:
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            thinking_placeholder = st.empty()
            thinking_placeholder.markdown(THINKING_HTML, unsafe_allow_html=True)

            start_time = time.time()
            result = engine.ask_detailed(question, short_answer)
            elapsed = time.time() - start_time

            thinking_placeholder.empty()

        st.session_state.messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
            "response_time": elapsed,
            "is_detailed": True,
        })
        st.rerun()

# Chat invoer
if prompt := st.chat_input("Stel een nieuwe vraag over de verkiezingen..."):
    # Sla vraag op en toon in chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # Toon denkanimatie terwijl antwoord wordt gegenereerd
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        thinking_placeholder = st.empty()
        thinking_placeholder.markdown(THINKING_HTML, unsafe_allow_html=True)

        start_time = time.time()
        result = engine.ask(prompt)
        elapsed = time.time() - start_time

        thinking_placeholder.empty()

    # Sla antwoord op in geschiedenis
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
        "response_time": elapsed,
    })

    # Herlaad pagina zodat bronnen en feedback-knoppen getoond worden
    st.rerun()

# Scroll naar het laatste bericht na rerun
if st.session_state.messages:
    import streamlit.components.v1 as components
    components.html(
        '<script>window.parent.document.querySelector("section.main").scrollTo(0, window.parent.document.querySelector("section.main").scrollHeight);</script>',
        height=0,
    )

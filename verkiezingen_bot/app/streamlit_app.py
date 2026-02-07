"""
Streamlit chat-interface voor de Verkiezingen Chatbot.
"""

import streamlit as st

from verkiezingen_bot.app.qa import QAEngine

# Pagina-instellingen
st.set_page_config(
    page_title="Verkiezingen Chatbot GR26",
    page_icon="\U0001f5f3\ufe0f",
    layout="centered",
)

# Custom styling
st.markdown("""
<style>
    .stApp {
        background-color: #fafafa;
    }
    .main-header {
        color: #c4122f;
        text-align: center;
        padding: 1rem 0;
    }
    .subtitle {
        color: #555;
        text-align: center;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .source-box {
        background-color: #f0f0f0;
        border-left: 4px solid #c4122f;
        padding: 0.8rem 1rem;
        margin-top: 0.5rem;
        border-radius: 0 4px 4px 0;
        font-size: 0.9rem;
    }
    .source-box a {
        color: #c4122f;
        text-decoration: none;
    }
    .source-box a:hover {
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">\U0001f5f3\ufe0f Verkiezingen Chatbot GR26</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Stel een vraag over de gemeenteraadsverkiezingen 2026</p>', unsafe_allow_html=True)


def render_sources(sources: list[dict]):
    """Toon bronverwijzingen onder een antwoord."""
    if not sources:
        return
    html = '<div class="source-box"><strong>Bronnen:</strong><ul>'
    for src in sources:
        titel = src.get("titel", "Onbekend")
        url = src.get("url", "")
        if url:
            html += f'<li><a href="{url}" target="_blank">{titel}</a></li>'
        else:
            html += f"<li>{titel}</li>"
    html += "</ul></div>"
    st.markdown(html, unsafe_allow_html=True)


@st.cache_resource
def load_engine():
    """Laad de QA engine (cached zodat het maar 1x gebeurt)."""
    return QAEngine()


# Laad engine
with st.spinner("Chatbot wordt geladen..."):
    engine = load_engine()

# Chat-geschiedenis
if "messages" not in st.session_state:
    st.session_state.messages = []

# Toon eerdere berichten
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            render_sources(message["sources"])

# Chat invoer
if prompt := st.chat_input("Stel je vraag over de verkiezingen..."):
    # Toon gebruikersvraag
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Genereer antwoord
    with st.chat_message("assistant"):
        with st.spinner("Even denken..."):
            result = engine.ask(prompt)

        st.markdown(result["answer"])
        render_sources(result["sources"])

    # Sla antwoord op in geschiedenis
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
    })

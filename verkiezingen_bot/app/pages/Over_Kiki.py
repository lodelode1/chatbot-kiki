"""Over Kiki — informatiepagina."""

import streamlit as st

st.set_page_config(page_title="Over Kiki", page_icon=":ballot_box:")

st.markdown("""
# Over Kiki

## Wat is Kiki?
Kiki is een experimentele chatbot die vragen beantwoordt over de
**gemeenteraadsverkiezingen 2026** in Nederland. Kiki doorzoekt de Toolkit
Verkiezingen van de Kiesraad en formuleert op basis van gevonden passages een
antwoord.

## Waar is Kiki's kennis op gebaseerd?
Kiki's kennis komt uit de **Toolkit Verkiezingen** van de Kiesraad. Dit omvat
instructies, handleidingen, modellen, nieuwsbrieven en overige documenten die
de Kiesraad beschikbaar stelt ter voorbereiding op de gemeenteraadsverkiezingen.

## Disclaimer
Kiki is **niet gemaakt door en niet goedgekeurd door de Kiesraad**. Het is een
onafhankelijk experiment met AI-toepassingen rond verkiezingsinformatie. De
Kiesraad is op geen enkele wijze verantwoordelijk voor de antwoorden die Kiki
geeft.

## Belangrijk om te weten
- **Kiki kan fouten maken.** Controleer belangrijke informatie altijd bij de
  officiële bronnen op [kiesraad.nl](https://www.kiesraad.nl).
- **Kiki heeft geen geheugen:** elke vraag wordt los beantwoord. Stel dus elke
  keer een complete vraag.
- **Kiki is geen vervanging** voor juridisch advies of de officiële
  Kiesraad-helpdesk.

## Hoe is Kiki gemaakt?
Kiki is ontwikkeld als experiment met AI-toepassingen voor
verkiezingsinformatie. De chatbot maakt gebruik van **Retrieval-Augmented
Generation (RAG)**: een techniek waarbij eerst relevante passages worden
opgezocht in de Toolkit, en vervolgens een taalmodel het antwoord formuleert op
basis van die passages.

Onder de motorkap:
- **Zoeken:** hybride zoeken (semantisch + trefwoord) met re-ranking
- **Taalmodel:** DeepSeek V3 via OpenRouter
- **Embeddings:** paraphrase-multilingual-MiniLM-L12-v2
- **Index:** FAISS (Facebook AI Similarity Search)
- **Interface:** Streamlit

## Feedback
Gebruik de duim-knoppen onder elk antwoord om aan te geven of een antwoord
nuttig was. Zo helpt u Kiki te verbeteren.
""")

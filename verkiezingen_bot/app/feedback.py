"""
Feedback opslag: Supabase (primair) met lokale CSV fallback.
"""

import csv
import os
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

# Pad voor lokale fallback CSV
FEEDBACK_CSV = Path(__file__).parent.parent / "data" / "feedback.csv"


def _get_supabase_config():
    """Haal Supabase URL en key op uit st.secrets of environment."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url:
        try:
            url = st.secrets["SUPABASE_URL"]
        except Exception:
            pass
    if not key:
        try:
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
    return url, key


def _save_to_supabase(question: str, answer: str, rating: str, comment: str) -> bool:
    """Sla feedback op in Supabase. Retourneert True bij succes."""
    url, key = _get_supabase_config()
    if not url or not key:
        return False

    try:
        response = requests.post(
            f"{url}/rest/v1/feedback",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "vraag": question,
                "antwoord": answer[:500],
                "beoordeling": rating,
                "toelichting": comment,
            },
            timeout=5,
        )
        return response.status_code == 201
    except Exception as e:
        print(f"Supabase fout: {e}")
        return False


def _save_to_csv(question: str, answer: str, rating: str, comment: str):
    """Lokale CSV fallback."""
    FEEDBACK_CSV.parent.mkdir(parents=True, exist_ok=True)
    file_exists = FEEDBACK_CSV.exists()

    with open(FEEDBACK_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                ["Tijdstip", "Vraag", "Antwoord", "Beoordeling", "Toelichting"]
            )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp, question, answer[:500], rating, comment])


def save_feedback(question: str, answer: str, rating: str, comment: str = ""):
    """
    Sla feedback op. Probeert eerst Supabase, anders lokale CSV.

    Args:
        question: De gestelde vraag
        answer: Het gegeven antwoord
        rating: "positief" of "negatief"
        comment: Optionele toelichting van de gebruiker
    """
    success = _save_to_supabase(question, answer, rating, comment)
    if not success:
        _save_to_csv(question, answer, rating, comment)

"""
Feedback opslag: Google Sheets (primair) met lokale CSV fallback.
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

# Pad voor lokale fallback CSV
FEEDBACK_CSV = Path(__file__).parent.parent / "data" / "feedback.csv"


def _get_gspread_client():
    """Maak een gspread client aan via st.secrets of .env."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # Probeer credentials uit st.secrets (Streamlit Cloud)
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except (KeyError, FileNotFoundError):
        pass

    # Probeer credentials uit environment variable (lokaal)
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)

    return None


def _save_to_sheets(question: str, answer: str, rating: str, comment: str) -> bool:
    """Sla feedback op in Google Sheets. Retourneert True bij succes."""
    client = _get_gspread_client()
    if client is None:
        return False

    try:
        # Sheet-naam uit secrets of default
        try:
            sheet_name = st.secrets["feedback_sheet_name"]
        except (KeyError, FileNotFoundError):
            sheet_name = os.getenv("FEEDBACK_SHEET_NAME", "Kiki Feedback")

        spreadsheet = client.open(sheet_name)
        worksheet = spreadsheet.sheet1

        # Maak headers aan als het sheet leeg is
        if worksheet.row_count == 0 or not worksheet.cell(1, 1).value:
            worksheet.append_row(
                ["Tijdstip", "Vraag", "Antwoord", "Beoordeling", "Toelichting"]
            )

        # Voeg feedback toe
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([
            timestamp,
            question,
            answer[:500],
            rating,
            comment,
        ])
        return True

    except Exception as e:
        print(f"Google Sheets fout: {e}")
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
    Sla feedback op. Probeert eerst Google Sheets, anders lokale CSV.

    Args:
        question: De gestelde vraag
        answer: Het gegeven antwoord
        rating: "positief" of "negatief"
        comment: Optionele toelichting van de gebruiker
    """
    success = _save_to_sheets(question, answer, rating, comment)
    if not success:
        _save_to_csv(question, answer, rating, comment)

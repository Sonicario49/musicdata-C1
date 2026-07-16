"""Extraction de données musicales par web scraping (source 2/5 : Web scraping).

Cible : le classement Spotify quotidien (Top 200 global) sur kworb.net, une page
HTML statique (pas de JS, robots.txt autorise le scraping : cf. https://kworb.net/robots.txt).
URL : https://kworb.net/spotify/country/global_daily.html

Ce script se contente de télécharger et sauvegarder la page HTML brute (avec
une vérification de structure minimale : la table attendue est bien présente).
Le parsing de la table (BeautifulSoup) et la normalisation vers le schéma
commun sont la responsabilité d'aggregation/aggregate.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHART_URL = "https://kworb.net/spotify/country/global_daily.html"
REQUEST_TIMEOUT = 10  # secondes
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; musicdata-project/1.0; projet certification RNCP)"}

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_HTML_PATH = RAW_DATA_DIR / "scraping_charts.html"


class ScrapingError(Exception):
    """Levée quand le scraping échoue de façon non récupérable."""


def fetch_page(url: str = CHART_URL) -> str:
    """Télécharge le HTML de la page de charts."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ScrapingError(f"Échec du téléchargement de {url} : {exc}") from exc
    return response.text


def check_page_structure(html: str) -> None:
    """Vérifie que la table attendue est présente (la page n'a pas changé de structure)."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("table", id="spotifydaily") is None:
        raise ScrapingError("Table #spotifydaily introuvable : structure de la page a changé ?")


def save_results(html: str) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML_PATH.write_text(html, encoding="utf-8")
    logger.info("Page brute sauvegardée : %s", OUTPUT_HTML_PATH)


def main() -> None:
    try:
        html = fetch_page()
        check_page_structure(html)
    except ScrapingError as exc:
        logger.error("Scraping interrompu : %s", exc)
        return

    save_results(html)
    logger.info("Scraping terminé avec succès.")


if __name__ == "__main__":
    main()

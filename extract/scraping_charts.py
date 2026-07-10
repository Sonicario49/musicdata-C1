"""Extraction de données musicales par web scraping (source 2/5 : Web scraping).

Cible : le classement Spotify quotidien (Top 200 global) sur kworb.net, une page
HTML statique (pas de JS, robots.txt autorise le scraping : cf. https://kworb.net/robots.txt).
URL : https://kworb.net/spotify/country/global_daily.html
"""

from __future__ import annotations

import csv
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CHART_URL = "https://kworb.net/spotify/country/global_daily.html"
REQUEST_TIMEOUT = 10  # secondes
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; musicdata-project/1.0; projet certification RNCP)"}

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


@dataclass
class Track:
    titre: str
    artiste: str
    genre: str
    duree_secondes: int
    date_sortie: str
    popularite: int  # streams quotidiens : utilisés comme proxy de popularité
    source: str = "scraping_charts"


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


def parse_int(text: str) -> int:
    """Convertit '4,125,535' -> 4125535. Retourne 0 si non convertible."""
    try:
        return int(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def parse_tracks(html: str) -> list[Track]:
    """Parse la table #spotifydaily et normalise chaque ligne vers le schéma commun."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="spotifydaily")
    if table is None:
        raise ScrapingError("Table #spotifydaily introuvable : structure de la page a changé ?")

    rows = table.find("tbody").find_all("tr")
    tracks: list[Track] = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            logger.warning("Ligne ignorée (colonnes manquantes) : %s", row.get_text(strip=True))
            continue

        title_link = cells[2].find("a", href=lambda h: h and "/track/" in h)
        artist_links = cells[2].find_all("a", href=lambda h: h and "/artist/" in h)
        if title_link is None or not artist_links:
            logger.warning("Ligne ignorée (artiste/titre introuvable) : %s", cells[2].get_text(strip=True))
            continue

        tracks.append(
            Track(
                titre=title_link.get_text(strip=True),
                artiste=", ".join(a.get_text(strip=True) for a in artist_links),
                genre="inconnu",  # non fourni par cette page de charts
                duree_secondes=0,  # non fourni par cette page de charts
                date_sortie="",  # non fourni par cette page de charts
                popularite=parse_int(cells[6].get_text()),  # streams quotidiens
            )
        )

    return tracks


def save_results(html: str, tracks: list[Track]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    html_path = RAW_DATA_DIR / "scraping_charts.html"
    html_path.write_text(html, encoding="utf-8")
    logger.info("Page brute sauvegardée (audit/traçabilité) : %s", html_path)

    csv_path = RAW_DATA_DIR / "scraping_tracks.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(tracks[0]).keys()))
        writer.writeheader()
        for track in tracks:
            writer.writerow(asdict(track))
    logger.info("Résultats normalisés sauvegardés : %s (%d lignes)", csv_path, len(tracks))


def main() -> None:
    try:
        html = fetch_page()
        tracks = parse_tracks(html)
    except ScrapingError as exc:
        logger.error("Scraping interrompu : %s", exc)
        return

    if not tracks:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    save_results(html, tracks)
    logger.info("Scraping terminé avec succès : %d morceaux.", len(tracks))


if __name__ == "__main__":
    main()

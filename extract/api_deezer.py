"""Extraction de données musicales via l'API publique Deezer (source 1/5 : Web API).

Documentation API : https://developers.deezer.com/api
Aucune authentification requise pour les endpoints utilisés ici.

Ce script se contente de récupérer et sauvegarder les payloads JSON bruts tels
que renvoyés par Deezer (schéma natif de l'API : "title", "artist.name",
"duration", "rank", "album.release_date", "album.genres"...). Aucun
renommage vers le schéma commun du projet, aucune conversion : cette
normalisation est la responsabilité d'aggregation/aggregate.py.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://api.deezer.com"
CHART_LIMIT = 50  # nombre de morceaux à récupérer dans le top chart
REQUEST_TIMEOUT = 10  # secondes
RATE_LIMIT_DELAY = 0.2  # secondes entre deux appels (quota Deezer : 50 req / 5s)

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_JSON_PATH = RAW_DATA_DIR / "deezer_raw.json"


class DeezerExtractionError(Exception):
    """Levée quand l'extraction Deezer échoue de façon non récupérable."""


class DeezerClient:
    """Petit client HTTP pour l'API publique Deezer."""

    def __init__(self, base_url: str = BASE_URL, timeout: int = REQUEST_TIMEOUT) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise DeezerExtractionError(f"Échec de la requête {url} : {exc}") from exc

        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            raise DeezerExtractionError(f"Erreur API Deezer sur {url} : {payload['error']}")
        return payload

    def get_chart_tracks(self, limit: int = CHART_LIMIT) -> list[dict]:
        """Récupère le top chart des morceaux les plus populaires (popularité = rank)."""
        data = self._get("/chart/0/tracks", params={"limit": limit})
        return data.get("data", [])

    def get_album(self, album_id: int) -> dict:
        """Récupère les détails d'un album (genre, date de sortie), absents du chart."""
        return self._get(f"/album/{album_id}")


def extract_raw_payloads(client: DeezerClient, limit: int = CHART_LIMIT) -> list[dict]:
    """Récupère le chart et l'album associé à chaque morceau, sans normalisation."""
    raw_payloads: list[dict] = []
    album_cache: dict[int, dict] = {}

    chart_tracks = client.get_chart_tracks(limit=limit)
    logger.info("Chart Deezer récupéré : %d morceaux", len(chart_tracks))

    for raw_track in chart_tracks:
        album_id = raw_track.get("album", {}).get("id")
        if album_id is None:
            logger.warning("Morceau sans album, ignoré : %s", raw_track.get("title"))
            continue

        if album_id not in album_cache:
            time.sleep(RATE_LIMIT_DELAY)
            try:
                album_cache[album_id] = client.get_album(album_id)
            except DeezerExtractionError as exc:
                logger.warning("Album %s inaccessible, morceau ignoré : %s", album_id, exc)
                continue

        raw_payloads.append({"track": raw_track, "album": album_cache[album_id]})

    return raw_payloads


def save_results(raw_payloads: list[dict]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(raw_payloads, f, ensure_ascii=False, indent=2)
    logger.info("Payloads bruts sauvegardés : %s (%d morceaux)", OUTPUT_JSON_PATH, len(raw_payloads))


def main() -> None:
    client = DeezerClient()
    try:
        raw_payloads = extract_raw_payloads(client)
    except DeezerExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    if not raw_payloads:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    save_results(raw_payloads)
    logger.info("Extraction Deezer terminée avec succès : %d morceaux.", len(raw_payloads))


if __name__ == "__main__":
    main()

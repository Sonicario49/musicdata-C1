"""Extraction de données musicales depuis une base SQL (source 4/5 : Base de données SQL).

Connexion à la base Postgres "source" (peuplée au préalable via db/seed_source_db.py
à partir d'un échantillon MusicBrainz) et requête d'extraction avec jointure.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Requête complexe : jointure sur 3 tables + filtre (durée connue) + condition (genre renseigné).
EXTRACTION_QUERY = """
    SELECT
        tracks.title AS titre,
        artists.name AS artiste,
        artists.genre AS genre,
        tracks.duration_ms AS duree_ms,
        albums.release_date AS date_sortie
    FROM tracks
    JOIN albums ON albums.id = tracks.album_id
    JOIN artists ON artists.id = albums.artist_id
    WHERE tracks.duration_ms IS NOT NULL
      AND artists.genre IS NOT NULL
      AND artists.genre <> 'inconnu'
    ORDER BY artists.name, albums.release_date;
"""


@dataclass
class Track:
    titre: str
    artiste: str
    genre: str
    duree_secondes: int
    date_sortie: str
    popularite: int  # non disponible via MusicBrainz -> 0
    source: str = "db_query"


class DbExtractionError(Exception):
    """Levée quand l'extraction depuis Postgres échoue de façon non récupérable."""


def get_connection():
    try:
        return psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
    except KeyError as exc:
        raise DbExtractionError(f"Variable d'environnement manquante : {exc}. Vérifie ton fichier .env.") from exc
    except psycopg2.OperationalError as exc:
        raise DbExtractionError(f"Connexion à Postgres impossible : {exc}") from exc


def extract_tracks(conn) -> list[Track]:
    try:
        with conn.cursor() as cur:
            cur.execute(EXTRACTION_QUERY)
            rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise DbExtractionError(f"Échec de la requête d'extraction : {exc}") from exc

    tracks = [
        Track(
            titre=titre,
            artiste=artiste,
            genre=genre,
            duree_secondes=(duree_ms or 0) // 1000,
            date_sortie=date_sortie or "",
            popularite=0,
        )
        for titre, artiste, genre, duree_ms, date_sortie in rows
    ]
    return tracks


def save_results(tracks: list[Track]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RAW_DATA_DIR / "db_query_tracks.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(tracks[0]).keys()))
        writer.writeheader()
        for track in tracks:
            writer.writerow(asdict(track))
    logger.info("Résultats normalisés sauvegardés : %s (%d lignes)", csv_path, len(tracks))


def main() -> None:
    try:
        conn = get_connection()
    except DbExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    try:
        tracks = extract_tracks(conn)
    except DbExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return
    finally:
        conn.close()

    if not tracks:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    save_results(tracks)
    logger.info("Extraction Postgres terminée avec succès : %d morceaux.", len(tracks))


if __name__ == "__main__":
    main()

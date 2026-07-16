"""Extraction de données musicales depuis une base SQL (source 4/5 : Base de données SQL).

Connexion à la base Postgres "source" (peuplée au préalable via db/seed_source_db.py
à partir d'un échantillon MusicBrainz) et requête d'extraction avec jointure.

La jointure sur les 3 tables reste ici : c'est la façon d'aller chercher la
donnée relationnelle (l'équivalent SQL d'un "GET" sur cette source). En
revanche, aucun renommage vers le schéma commun du projet (titre/artiste/...)
ni conversion d'unité : les colonnes natives des tables sont conservées telles
quelles, l'harmonisation étant la responsabilité d'aggregation/aggregate.py.
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_CSV_PATH = RAW_DATA_DIR / "db_query_tracks.csv"

# Jointure sur 3 tables + filtre (durée connue) + condition (genre renseigné),
# colonnes natives (pas d'alias vers le schéma commun).
EXTRACTION_QUERY = """
    SELECT
        tracks.title,
        artists.name AS artist_name,
        artists.genre,
        tracks.duration_ms,
        albums.release_date
    FROM tracks
    JOIN albums ON albums.id = tracks.album_id
    JOIN artists ON artists.id = albums.artist_id
    WHERE tracks.duration_ms IS NOT NULL
      AND artists.genre IS NOT NULL
      AND artists.genre <> 'inconnu'
    ORDER BY artists.name, albums.release_date;
"""


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


def extract_rows(conn) -> tuple[list[str], list[tuple]]:
    """Exécute la jointure et renvoie les lignes brutes avec les noms de colonnes natifs."""
    try:
        with conn.cursor() as cur:
            cur.execute(EXTRACTION_QUERY)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise DbExtractionError(f"Échec de la requête d'extraction : {exc}") from exc
    return columns, rows


def save_results(columns: list[str], rows: list[tuple]) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([*columns, "source"])
        for row in rows:
            writer.writerow([*row, "db_query"])
    logger.info("Résultats bruts sauvegardés : %s (%d lignes)", OUTPUT_CSV_PATH, len(rows))


def main() -> None:
    try:
        conn = get_connection()
    except DbExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    try:
        columns, rows = extract_rows(conn)
    except DbExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return
    finally:
        conn.close()

    if not rows:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    save_results(columns, rows)
    logger.info("Extraction Postgres terminée avec succès : %d morceaux.", len(rows))


if __name__ == "__main__":
    main()

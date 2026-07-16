"""Extraction de données musicales via DuckDB (source 5/5 : Système Big Data).

Dataset : "Spotify Huge Track Analysis Dataset" (Hugging Face, Gildas Le Drogoff).
Téléchargement manuel requis : placer spotify-huge-audio-features.parquet
(~4.1 Go, 56,3M lignes) sous data/external/ avant d'exécuter ce script.
Détail du schéma : data/external/README_spotify_huge_audio_features.md

Ce fichier est un vrai jeu de données Big Data (56 millions de lignes, format
Parquet colonnaire), impossible à charger entièrement en mémoire avec pandas.
DuckDB interroge directement le Parquet sur disque : le filtre de popularité
est appliqué en predicate pushdown (DuckDB élimine les row groups Parquet hors
seuil grâce à leurs statistiques min/max, sans lire les colonnes non
sélectionnées ni matérialiser les 56M lignes en mémoire).

Aucune normalisation vers le schéma commun ici : on ne fait qu'extraire et
filtrer. L'harmonisation (renommage, conversion ms -> s, genre absent de cette
source) est de la responsabilité d'aggregation/aggregate.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PARQUET = PROJECT_ROOT / "data" / "external" / "spotify-huge-audio-features.parquet"
OUTPUT_PARQUET_PATH = PROJECT_ROOT / "data" / "raw" / "bigdata_duckdb_tracks.parquet"

# Seuil de popularité : filtre les morceaux significatifs plutôt que de
# ressortir les 56,3M lignes brutes du fichier source.
MIN_POPULARITY = 50

# Colonnes natives du Parquet source, sans renommage ni conversion d'unité.
# Le chemin de sortie de COPY TO doit être un littéral (pas de paramètre lié
# possible côté DuckDB) : il est injecté via f-string, mais reste un chemin
# interne fixe (data/raw/...), jamais une entrée utilisateur.
EXTRACTION_QUERY = f"""
    COPY (
        SELECT
            track_name,
            artist_name,
            album_release_date,
            duration_ms,
            track_popularity,
            'bigdata_duckdb' AS source
        FROM read_parquet(?)
        WHERE track_popularity >= ?
    ) TO '{OUTPUT_PARQUET_PATH.as_posix()}' (FORMAT PARQUET)
"""


class BigDataExtractionError(Exception):
    """Levée quand l'extraction DuckDB échoue de façon non récupérable."""


def check_source_file() -> None:
    if not SOURCE_PARQUET.exists():
        raise BigDataExtractionError(
            f"Fichier source introuvable : {SOURCE_PARQUET}\n"
            "Place spotify-huge-audio-features.parquet dans data/external/ "
            "(voir data/external/README_spotify_huge_audio_features.md)."
        )


def extract_tracks() -> int:
    """Filtre le Parquet source vers data/raw/, entièrement via DuckDB (pas de pandas)."""
    OUTPUT_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(EXTRACTION_QUERY, [str(SOURCE_PARQUET), MIN_POPULARITY])
        (row_count,) = con.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(OUTPUT_PARQUET_PATH)]
        ).fetchone()
        return row_count
    except duckdb.Error as exc:
        raise BigDataExtractionError(f"Échec de la requête DuckDB : {exc}") from exc
    finally:
        con.close()


def main() -> None:
    try:
        check_source_file()
        row_count = extract_tracks()
    except BigDataExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    if row_count == 0:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    logger.info("Extraction DuckDB : %d morceaux (popularité >= %d)", row_count, MIN_POPULARITY)
    logger.info("Résultats bruts sauvegardés : %s", OUTPUT_PARQUET_PATH)
    logger.info("Extraction Big Data (DuckDB) terminée avec succès.")


if __name__ == "__main__":
    main()

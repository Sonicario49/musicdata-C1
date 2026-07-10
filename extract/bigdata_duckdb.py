"""Extraction de données musicales via DuckDB (source 5/5 : Système Big Data).

Dataset : "Spotify Dataset 1921-2020, 600k+ Tracks" (Kaggle, yamaerenay).
Téléchargement manuel requis : placer tracks.csv (~586k lignes) et artists.csv
(~1.16M lignes) sous data/external/ avant d'exécuter ce script.
https://www.kaggle.com/datasets/yamaerenay/spotify-dataset-19212020-600k-tracks

DuckDB lit et joint directement les deux fichiers CSV bruts (sans les charger
entièrement en mémoire via pandas), ce qui démontre l'intérêt d'un moteur
analytique colonne-orienté sur un volume que pandas gère plus difficilement.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACKS_CSV = PROJECT_ROOT / "data" / "external" / "tracks.csv"
ARTISTS_CSV = PROJECT_ROOT / "data" / "external" / "artists.csv"
OUTPUT_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "bigdata_duckdb_tracks.csv"

# Seuil de popularité : filtre les morceaux significatifs plutôt que de
# ressortir les ~587k lignes brutes du fichier source.
MIN_POPULARITY = 50

# Jointure tracks/artists + parsing des colonnes listes Python ("['pop']")
# via regexp_extract, entièrement en SQL DuckDB sur les fichiers CSV bruts.
EXTRACTION_QUERY = """
    WITH parsed_tracks AS (
        SELECT
            name AS titre,
            regexp_extract(artists, '''([^'']*)''', 1) AS artiste,
            regexp_extract(id_artists, '''([^'']*)''', 1) AS artist_id,
            duration_ms,
            release_date,
            popularity
        FROM read_csv_auto(?)
        WHERE duration_ms > 0 AND popularity >= ?
    ),
    parsed_artists AS (
        SELECT id, regexp_extract(genres, '''([^'']*)''', 1) AS genre
        FROM read_csv_auto(?)
    )
    SELECT
        t.titre,
        t.artiste,
        COALESCE(NULLIF(a.genre, ''), 'inconnu') AS genre,
        (t.duration_ms // 1000) AS duree_secondes,
        t.release_date AS date_sortie,
        t.popularity AS popularite
    FROM parsed_tracks t
    LEFT JOIN parsed_artists a ON a.id = t.artist_id
    ORDER BY t.popularity DESC;
"""


class BigDataExtractionError(Exception):
    """Levée quand l'extraction DuckDB échoue de façon non récupérable."""


def check_source_files() -> None:
    missing = [str(p) for p in (TRACKS_CSV, ARTISTS_CSV) if not p.exists()]
    if missing:
        raise BigDataExtractionError(
            f"Fichier(s) source introuvable(s) : {missing}\n"
            "Télécharge le dataset sur "
            "https://www.kaggle.com/datasets/yamaerenay/spotify-dataset-19212020-600k-tracks "
            "et place tracks.csv + artists.csv dans data/external/."
        )


def extract_tracks() -> "duckdb.DuckDBPyRelation":
    con = duckdb.connect()  # base DuckDB en mémoire, initialisation de la connexion
    try:
        result = con.execute(EXTRACTION_QUERY, [str(TRACKS_CSV), MIN_POPULARITY, str(ARTISTS_CSV)])
        return result.df()
    except duckdb.Error as exc:
        raise BigDataExtractionError(f"Échec de la requête DuckDB : {exc}") from exc
    finally:
        con.close()


def save_results(df) -> None:
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.insert(len(df.columns), "source", "bigdata_duckdb")
    df.to_csv(OUTPUT_CSV_PATH, index=False, encoding="utf-8")
    logger.info("Résultats normalisés sauvegardés : %s (%d lignes)", OUTPUT_CSV_PATH, len(df))


def main() -> None:
    try:
        check_source_files()
        df = extract_tracks()
    except BigDataExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    if df.empty:
        logger.error("Aucun morceau extrait, rien à sauvegarder.")
        return

    logger.info("Extraction DuckDB : %d morceaux (popularité >= %d)", len(df), MIN_POPULARITY)
    save_results(df)
    logger.info("Extraction Big Data (DuckDB) terminée avec succès.")


if __name__ == "__main__":
    main()

"""Extraction de données musicales depuis un fichier (source 3/5 : Fichier CSV).

Dataset : "Spotify Tracks Dataset" (Kaggle, maharshipandya/spotify-tracks-dataset).
Téléchargement manuel requis (compte Kaggle) : placer le CSV téléchargé sous
data/external/spotify_tracks_kaggle.csv avant d'exécuter ce script.
https://www.kaggle.com/datasets/maharshipandya/spotify-tracks-dataset
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV_PATH = PROJECT_ROOT / "data" / "external" / "spotify_tracks_kaggle.csv"
OUTPUT_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "file_csv_tracks.csv"

REQUIRED_SOURCE_COLUMNS = ["track_name", "artists", "track_genre", "duration_ms", "popularity"]
TARGET_COLUMNS = ["titre", "artiste", "genre", "duree_secondes", "date_sortie", "popularite", "source"]


class FileExtractionError(Exception):
    """Levée quand l'extraction depuis le fichier échoue de façon non récupérable."""


def load_dataset(path: Path = INPUT_CSV_PATH) -> pd.DataFrame:
    """Ouvre le CSV source. Équivalent ici de l'« initialisation de connexion externe »."""
    if not path.exists():
        raise FileExtractionError(
            f"Fichier introuvable : {path}\n"
            "Télécharge le dataset sur "
            "https://www.kaggle.com/datasets/maharshipandya/spotify-tracks-dataset "
            f"et place le CSV à cet emplacement."
        )
    try:
        return pd.read_csv(path)
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise FileExtractionError(f"Impossible de parser le CSV {path} : {exc}") from exc


def validate_columns(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_SOURCE_COLUMNS if col not in df.columns]
    if missing:
        raise FileExtractionError(
            f"Colonnes attendues manquantes dans le CSV : {missing}. "
            f"Colonnes trouvées : {list(df.columns)}"
        )


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et normalise le dataset brut vers le schéma commun du projet."""
    df = df.dropna(subset=["track_name", "artists"])
    df = df.drop_duplicates(subset=["track_name", "artists"])
    df = df[df["duration_ms"] > 0]

    result = pd.DataFrame(
        {
            "titre": df["track_name"].str.strip(),
            "artiste": df["artists"].str.strip(),
            "genre": df["track_genre"].str.strip().str.lower(),
            "duree_secondes": (df["duration_ms"] // 1000).astype(int),
            "date_sortie": "",  # non fourni par ce dataset
            "popularite": df["popularity"].astype(int),
            "source": "file_csv",
        }
    )
    return result.reset_index(drop=True)


def save_results(df: pd.DataFrame) -> None:
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV_PATH, index=False, encoding="utf-8")
    logger.info("Résultats normalisés sauvegardés : %s (%d lignes)", OUTPUT_CSV_PATH, len(df))


def main() -> None:
    try:
        raw_df = load_dataset()
        validate_columns(raw_df)
    except FileExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    logger.info("Dataset chargé : %d lignes brutes", len(raw_df))

    clean_df = clean_dataset(raw_df)
    if clean_df.empty:
        logger.error("Aucune ligne exploitable après nettoyage, rien à sauvegarder.")
        return

    logger.info("Dataset nettoyé : %d lignes conservées", len(clean_df))
    save_results(clean_df)
    logger.info("Extraction fichier CSV terminée avec succès.")


if __name__ == "__main__":
    main()

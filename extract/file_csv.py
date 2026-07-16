"""Extraction de données musicales depuis un fichier (source 3/5 : Fichier CSV).

Dataset : "Spotify Tracks Dataset" (Kaggle, maharshipandya/spotify-tracks-dataset).
Téléchargement manuel requis (compte Kaggle) : placer le CSV téléchargé sous
data/external/spotify_tracks_kaggle.csv avant d'exécuter ce script.
https://www.kaggle.com/datasets/maharshipandya/spotify-tracks-dataset

Ce script copie le CSV tel quel dans data/raw/, avec ses colonnes natives
(track_name, artists, track_genre, duration_ms, popularity...), après une
simple vérification de présence des colonnes attendues. Aucun nettoyage ni
renommage : cette normalisation est la responsabilité d'aggregation/aggregate.py.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV_PATH = PROJECT_ROOT / "data" / "external" / "spotify_tracks_kaggle.csv"
OUTPUT_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "file_csv_tracks.csv"

REQUIRED_SOURCE_COLUMNS = ["track_name", "artists", "track_genre", "duration_ms", "popularity"]


class FileExtractionError(Exception):
    """Levée quand l'extraction depuis le fichier échoue de façon non récupérable."""


def check_source_file(path: Path = INPUT_CSV_PATH) -> None:
    """Vérifie que le fichier existe et contient les colonnes attendues, sans le charger en entier."""
    if not path.exists():
        raise FileExtractionError(
            f"Fichier introuvable : {path}\n"
            "Télécharge le dataset sur "
            "https://www.kaggle.com/datasets/maharshipandya/spotify-tracks-dataset "
            f"et place le CSV à cet emplacement."
        )
    try:
        header = pd.read_csv(path, nrows=0)
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise FileExtractionError(f"Impossible de parser le CSV {path} : {exc}") from exc

    missing = [col for col in REQUIRED_SOURCE_COLUMNS if col not in header.columns]
    if missing:
        raise FileExtractionError(
            f"Colonnes attendues manquantes dans le CSV : {missing}. "
            f"Colonnes trouvées : {list(header.columns)}"
        )


def save_results(source_path: Path = INPUT_CSV_PATH) -> None:
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, OUTPUT_CSV_PATH)
    logger.info("Fichier source copié tel quel : %s", OUTPUT_CSV_PATH)


def main() -> None:
    try:
        check_source_file()
    except FileExtractionError as exc:
        logger.error("Extraction interrompue : %s", exc)
        return

    save_results()
    logger.info("Extraction fichier CSV terminée avec succès.")


if __name__ == "__main__":
    main()

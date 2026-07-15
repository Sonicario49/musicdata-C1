"""Agrégation des 5 sources extraites en un seul jeu de données final (C3).

Technos : Python + pandas (choix justifié ci-dessous, pas de SQL pour cette étape).

Pourquoi pandas plutôt que SQL ici : les 5 sources sont déjà matérialisées en CSV
indépendants dans data/raw/ (pas dans un même moteur SQL, Postgres, DuckDB et de
simples fichiers coexistent). Les recharger dans une seule base pour faire un JOIN SQL
ajouterait une étape inutile ; pandas permet de concaténer et nettoyer ces CSV
hétérogènes directement, avec un contrôle fin (via du code Python lisible) sur chaque
règle d'harmonisation ci-dessous.

Entrée  : data/raw/{api_deezer,scraping,file_csv,db_query,bigdata_duckdb}_tracks.csv
Sortie  : data/processed/musicdata_final.csv

Ordre de traitement (cf. main()) :
  1. Chargement des 5 CSV sources + concaténation (une colonne "source" distingue déjà
     leur origine, ajoutée par chaque script d'extraction).
  2. Harmonisation du genre (casse).
  3. Harmonisation de la date de sortie (dates partielles -> ISO complet YYYY-MM-DD).
  4. Harmonisation de la popularité (échelles incomparables -> score relatif 0-100
     par source).
  5. Suppression des entrées corrompues (titre/artiste manquant, durée aberrante).
  6. Suppression des doublons (même titre+artiste), en gardant la ligne la plus
     complète parmi les doublons.
  7. Sauvegarde du jeu de données final.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "musicdata_final.csv"

SOURCE_FILES = [
    "deezer_tracks.csv",
    "scraping_tracks.csv",
    "file_csv_tracks.csv",
    "db_query_tracks.csv",
    "bigdata_duckdb_tracks.csv",
]

# Durée jugée aberrante pour un morceau (0 = "durée inconnue", conservé tel quel).
MAX_DUREE_SECONDES = 3600 * 2  # 2h


class AggregationError(Exception):
    """Levée quand l'agrégation échoue de façon non récupérable."""


def load_sources() -> pd.DataFrame:
    """Charge et concatène les CSV normalisés produits par les 5 scripts d'extraction."""
    frames = []
    for filename in SOURCE_FILES:
        path = RAW_DATA_DIR / filename
        if not path.exists():
            logger.warning("Source absente, ignorée : %s", path)
            continue
        df = pd.read_csv(path, dtype={"date_sortie": str})
        frames.append(df)
        logger.info("Chargé %s : %d lignes", filename, len(df))

    if not frames:
        raise AggregationError("Aucune source disponible dans data/raw/. Lance les scripts d'extraction d'abord.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Total après concaténation : %d lignes", len(combined))
    return combined


def harmonize_genre(df: pd.DataFrame) -> pd.DataFrame:
    """Uniformise la casse du genre (ex: Deezer renvoie 'Rap/Hip Hop', les autres sources
    sont déjà en minuscules) : tout en minuscules, valeurs vides -> 'inconnu'."""
    df["genre"] = df["genre"].fillna("inconnu").astype(str).str.strip().str.lower()
    df.loc[df["genre"] == "", "genre"] = "inconnu"
    return df


def harmonize_date(df: pd.DataFrame) -> pd.DataFrame:
    """Complète les dates partielles en ISO YYYY-MM-DD.

    Constat réel sur les données du projet : le dataset Big Data (bigdata_duckdb) contient
    des dates au format YYYY seul (6 603 lignes) ou YYYY-MM (138 lignes) en plus du format
    complet (69 102 lignes). On les complète par convention au 1er janvier / 1er du mois
    plutôt que de les rejeter, pour ne pas perdre l'information "année de sortie" qui reste
    exploitable pour l'analyse.
    """
    date_str = df["date_sortie"].fillna("").astype(str).str.strip()

    is_year_only = date_str.str.match(r"^\d{4}$")
    is_year_month = date_str.str.match(r"^\d{4}-\d{2}$")

    date_str = date_str.where(~is_year_only, date_str + "-01-01")
    date_str = date_str.where(~is_year_month, date_str + "-01")

    df["date_sortie"] = date_str
    return df


def harmonize_popularity(df: pd.DataFrame) -> pd.DataFrame:
    """Ramène la popularité de chaque source à une échelle commune 0-100.

    Les échelles brutes ne sont pas comparables entre sources : rank Deezer
    (centaines de milliers), streams/jour kworb (millions), score Kaggle (0-100 déjà),
    popularité MusicBrainz absente (0 constant). On normalise donc par min-max
    *au sein de chaque source* : le résultat reste une popularité relative à sa
    plateforme d'origine, pas une métrique absolue inter-plateformes (documenté aussi
    dans docs/tableau_sources.md).
    """
    df["popularite"] = pd.to_numeric(df["popularite"], errors="coerce").fillna(0)

    def normalize(group: pd.Series) -> pd.Series:
        low, high = group.min(), group.max()
        if high == low:
            return group  # pas de signal de popularité exploitable (ex: MusicBrainz -> tout à 0)
        return (group - low) / (high - low) * 100

    df["popularite"] = df.groupby("source")["popularite"].transform(normalize).round().astype(int)
    return df


def remove_corrupted(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les lignes corrompues : titre/artiste manquant, durée aberrante."""
    before = len(df)

    df["titre"] = df["titre"].astype(str).str.strip()
    df["artiste"] = df["artiste"].astype(str).str.strip()
    df["duree_secondes"] = pd.to_numeric(df["duree_secondes"], errors="coerce").fillna(0).astype(int)

    valid = (
        (df["titre"] != "")
        & (df["titre"].str.lower() != "nan")
        & (df["artiste"] != "")
        & (df["artiste"].str.lower() != "nan")
        & (df["duree_secondes"] >= 0)
        & (df["duree_secondes"] <= MAX_DUREE_SECONDES)
    )
    df = df[valid].copy()
    logger.info("Entrées corrompues supprimées : %d", before - len(df))
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Supprime les doublons (même titre+artiste) en gardant la ligne la plus complète."""
    before = len(df)

    dedup_key = (
        df["titre"].str.lower().str.strip() + "||" + df["artiste"].str.lower().str.strip()
    )
    completeness = (
        (df["genre"] != "inconnu").astype(int)
        + (df["duree_secondes"] > 0).astype(int)
        + (df["date_sortie"] != "").astype(int)
        + (df["popularite"] > 0).astype(int)
    )
    df = df.assign(_dedup_key=dedup_key, _completeness=completeness)
    df = df.sort_values("_completeness", ascending=False)
    df = df.drop_duplicates(subset="_dedup_key", keep="first")
    df = df.drop(columns=["_dedup_key", "_completeness"]).reset_index(drop=True)

    logger.info("Doublons supprimés : %d", before - len(df))
    return df


def save_final(df: pd.DataFrame) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    columns = ["titre", "artiste", "genre", "duree_secondes", "date_sortie", "popularite", "source"]
    df[columns].to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    logger.info("Jeu de données final sauvegardé : %s (%d lignes)", OUTPUT_PATH, len(df))


def main() -> None:
    try:
        df = load_sources()
    except AggregationError as exc:
        logger.error("Agrégation interrompue : %s", exc)
        return

    df = harmonize_genre(df)
    df = harmonize_date(df)
    df = harmonize_popularity(df)
    df = remove_corrupted(df)
    df = deduplicate(df)

    if df.empty:
        logger.error("Jeu de données final vide, rien à sauvegarder.")
        return

    save_final(df)
    logger.info("Agrégation terminée avec succès : %d morceaux dans le jeu final.", len(df))


if __name__ == "__main__":
    main()

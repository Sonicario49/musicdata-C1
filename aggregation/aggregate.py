"""Agrégation des 5 sources extraites en un seul jeu de données final (C3).

Technos : Python + pandas (choix justifié ci-dessous, pas de SQL pour cette étape).

Chaque script d'extraction ne sauvegarde que la donnée brute, dans le format
natif renvoyé par sa source (JSON pour l'API Deezer, HTML pour le scraping,
CSV aux colonnes natives pour le fichier Kaggle et pour la requête SQL,
Parquet aux colonnes natives pour la source Big Data). Aucune de ces sources
n'est pré-normalisée vers un schéma commun : c'est le rôle de ce module, seul
endroit du pipeline où vit la logique de transformation (le "T" d'ETL), de la
parser, la nettoyer et l'harmoniser.

Pourquoi pandas plutôt que SQL ici : les 5 sources sont des fichiers
indépendants et hétérogènes dans data/raw/ (JSON, HTML, CSV, Parquet), pas
déjà matérialisées dans un même moteur SQL. Les recharger dans une seule base
pour faire un JOIN SQL ajouterait une étape inutile ; pandas permet de parser
et harmoniser directement ces formats hétérogènes, avec un contrôle fin (via
du code Python lisible) sur chaque règle ci-dessous.

Entrée  : data/raw/{deezer_raw.json, scraping_charts.html, file_csv_tracks.csv,
          db_query_tracks.csv, bigdata_duckdb_tracks.parquet}
Sortie  : data/processed/musicdata_final.parquet

Ordre de traitement (cf. main()) :
  1. Parsing de chaque source brute vers le schéma commun (une colonne
     "source" distingue leur origine) + concaténation.
  2. Harmonisation du genre (casse).
  3. Harmonisation de la date de sortie (valeurs manquantes -> chaîne vide).
  4. Harmonisation de la popularité (échelles incomparables -> score relatif
     0-100 par source).
  5. Suppression des entrées corrompues (titre/artiste manquant, durée aberrante).
  6. Suppression des doublons (même titre+artiste), en gardant la ligne la plus
     complète parmi les doublons.
  7. Sauvegarde du jeu de données final en Parquet (format colonnaire,
     cohérent avec le volume et l'argument Big Data du projet).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "musicdata_final.parquet"

COMMON_COLUMNS = ["titre", "artiste", "genre", "duree_secondes", "date_sortie", "popularite", "source"]

# Durée jugée aberrante pour un morceau (0 = "durée inconnue", conservé tel quel).
MAX_DUREE_SECONDES = 3600 * 2  # 2h


class AggregationError(Exception):
    """Levée quand l'agrégation échoue de façon non récupérable."""


def parse_int(text) -> int:
    """Convertit '4,125,535' -> 4125535. Retourne 0 si non convertible."""
    try:
        return int(str(text).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def load_deezer() -> pd.DataFrame:
    """Parse les payloads JSON bruts de l'API Deezer (schéma natif : title, artist.name,
    duration, rank, album.release_date, album.genres...)."""
    path = RAW_DATA_DIR / "deezer_raw.json"
    if not path.exists():
        logger.warning("Source absente, ignorée : %s", path)
        return pd.DataFrame(columns=COMMON_COLUMNS)

    payloads = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for payload in payloads:
        track, album = payload["track"], payload["album"]
        genres = album.get("genres", {}).get("data", [])
        rows.append(
            {
                "titre": track.get("title", ""),
                "artiste": track.get("artist", {}).get("name", ""),
                "genre": genres[0]["name"] if genres else "inconnu",
                "duree_secondes": track.get("duration", 0),
                "date_sortie": album.get("release_date", ""),
                "popularite": track.get("rank", 0),
                "source": "api_deezer",
            }
        )
    df = pd.DataFrame(rows, columns=COMMON_COLUMNS)
    logger.info("Chargé deezer_raw.json : %d lignes", len(df))
    return df


def load_scraping() -> pd.DataFrame:
    """Parse la page HTML brute de kworb.net (table #spotifydaily)."""
    path = RAW_DATA_DIR / "scraping_charts.html"
    if not path.exists():
        logger.warning("Source absente, ignorée : %s", path)
        return pd.DataFrame(columns=COMMON_COLUMNS)

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    table = soup.find("table", id="spotifydaily")
    if table is None:
        raise AggregationError(f"Table #spotifydaily introuvable dans {path} : structure a changé ?")

    rows = []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        title_link = cells[2].find("a", href=lambda h: h and "/track/" in h)
        artist_links = cells[2].find_all("a", href=lambda h: h and "/artist/" in h)
        if title_link is None or not artist_links:
            continue

        rows.append(
            {
                "titre": title_link.get_text(strip=True),
                "artiste": ", ".join(a.get_text(strip=True) for a in artist_links),
                "genre": "inconnu",  # non fourni par cette page de charts
                "duree_secondes": 0,  # non fourni par cette page de charts
                "date_sortie": "",  # non fourni par cette page de charts
                "popularite": parse_int(cells[6].get_text()),  # streams quotidiens
                "source": "scraping_charts",
            }
        )
    df = pd.DataFrame(rows, columns=COMMON_COLUMNS)
    logger.info("Chargé scraping_charts.html : %d lignes", len(df))
    return df


def load_file_csv() -> pd.DataFrame:
    """Parse le CSV Kaggle natif (track_name, artists, track_genre, duration_ms, popularity)."""
    path = RAW_DATA_DIR / "file_csv_tracks.csv"
    if not path.exists():
        logger.warning("Source absente, ignorée : %s", path)
        return pd.DataFrame(columns=COMMON_COLUMNS)

    raw = pd.read_csv(path)
    raw = raw.dropna(subset=["track_name", "artists"])
    raw = raw.drop_duplicates(subset=["track_name", "artists"])
    raw = raw[raw["duration_ms"] > 0]

    df = pd.DataFrame(
        {
            "titre": raw["track_name"].str.strip(),
            "artiste": raw["artists"].str.strip(),
            "genre": raw["track_genre"].str.strip().str.lower(),
            "duree_secondes": (raw["duration_ms"] // 1000).astype(int),
            "date_sortie": "",  # non fourni par ce dataset
            "popularite": raw["popularity"].astype(int),
            "source": "file_csv",
        }
    ).reset_index(drop=True)
    logger.info("Chargé file_csv_tracks.csv : %d lignes", len(df))
    return df


def load_db_query() -> pd.DataFrame:
    """Parse le CSV aux colonnes natives Postgres (title, artist_name, genre, duration_ms,
    release_date), issu de la jointure tracks/albums/artists."""
    path = RAW_DATA_DIR / "db_query_tracks.csv"
    if not path.exists():
        logger.warning("Source absente, ignorée : %s", path)
        return pd.DataFrame(columns=COMMON_COLUMNS)

    raw = pd.read_csv(path, dtype={"release_date": str})
    df = pd.DataFrame(
        {
            "titre": raw["title"],
            "artiste": raw["artist_name"],
            "genre": raw["genre"],
            "duree_secondes": (raw["duration_ms"].fillna(0) // 1000).astype(int),
            "date_sortie": raw["release_date"].fillna(""),
            "popularite": 0,  # non disponible via cette source
            "source": "db_query",
        }
    )
    logger.info("Chargé db_query_tracks.csv : %d lignes", len(df))
    return df


def load_bigdata_duckdb() -> pd.DataFrame:
    """Parse le Parquet aux colonnes natives (track_name, artist_name, album_release_date,
    duration_ms, track_popularity), filtré par DuckDB depuis les 56M lignes de la source."""
    path = RAW_DATA_DIR / "bigdata_duckdb_tracks.parquet"
    if not path.exists():
        logger.warning("Source absente, ignorée : %s", path)
        return pd.DataFrame(columns=COMMON_COLUMNS)

    raw = pd.read_parquet(path)
    date_sortie = pd.to_datetime(raw["album_release_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    df = pd.DataFrame(
        {
            "titre": raw["track_name"],
            "artiste": raw["artist_name"],
            "genre": "inconnu",  # non fourni par cette source (pas de métadonnée de genre)
            "duree_secondes": (raw["duration_ms"].fillna(0) // 1000).astype(int),
            "date_sortie": date_sortie.fillna(""),
            "popularite": raw["track_popularity"].fillna(0).astype(int),
            "source": "bigdata_duckdb",
        }
    )
    logger.info("Chargé bigdata_duckdb_tracks.parquet : %d lignes", len(df))
    return df


SOURCE_LOADERS = [load_deezer, load_scraping, load_file_csv, load_db_query, load_bigdata_duckdb]


def load_sources() -> pd.DataFrame:
    """Parse et concatène les 5 sources brutes (chacune dans son format natif)."""
    frames = [loader() for loader in SOURCE_LOADERS]
    frames = [f for f in frames if not f.empty]

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
    """Normalise la date de sortie : chaque loader produit déjà du ISO YYYY-MM-DD ou une
    chaîne vide (source sans date) ; on ne fait ici que combler les valeurs manquantes."""
    df["date_sortie"] = df["date_sortie"].fillna("").astype(str).str.strip()
    return df


def harmonize_popularity(df: pd.DataFrame) -> pd.DataFrame:
    """Ramène la popularité de chaque source à une échelle commune 0-100.

    Les échelles brutes ne sont pas comparables entre sources : rank Deezer,
    streams/jour kworb (millions), score Kaggle et Big Data (0-100 déjà),
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
    df[columns].to_parquet(OUTPUT_PATH, index=False)
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

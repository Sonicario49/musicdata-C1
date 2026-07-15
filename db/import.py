"""Import du jeu de données final (C3) dans la base Postgres cible (C4).

Technos : PostgreSQL + psycopg2 (pas d'ORM, cf. docs/requetes_sql.md pour la justification
déjà donnée en C2, même logique ici : peu de requêtes, on garde la visibilité du SQL brut).

Entrée  : data/processed/musicdata_final.csv (produit par aggregation/aggregate.py)
Cible   : base Postgres "musicdata" (distincte de "musicdata_source" utilisée en C1/C2 pour
          l'extraction, celle-ci est la base finale du projet, modélisée en db/schema.sql).

Ordre de traitement :
  1. Création de la base cible si elle n'existe pas encore.
  2. Application du schéma (db/schema.sql, idempotent : CREATE TABLE/INDEX IF NOT EXISTS).
  3. Chargement du CSV final.
  4. Insertion des artistes et genres uniques (ON CONFLICT DO NOTHING sur le nom).
  5. Insertion des morceaux, avec résolution des clés étrangères vers artiste/genre.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
INPUT_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "musicdata_final.csv"

PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]
PG_TARGET_DB = os.environ.get("POSTGRES_TARGET_DB", "musicdata")


class ImportError_(Exception):
    """Levée quand l'import échoue de façon non récupérable."""


def ensure_database_exists() -> None:
    """Crée la base cible si besoin, en se connectant à la base 'postgres' par défaut."""
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname="postgres")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_TARGET_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{PG_TARGET_DB}"')
                logger.info("Base '%s' créée.", PG_TARGET_DB)
    finally:
        conn.close()


def get_target_connection():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_TARGET_DB
    )


def apply_schema(conn) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Schéma appliqué depuis %s", SCHEMA_PATH)


def load_final_dataset() -> pd.DataFrame:
    if not INPUT_CSV_PATH.exists():
        raise ImportError_(
            f"Fichier introuvable : {INPUT_CSV_PATH}. Lance d'abord aggregation/aggregate.py."
        )
    df = pd.read_csv(INPUT_CSV_PATH, dtype={"date_sortie": str})
    df["date_sortie"] = df["date_sortie"].apply(lambda v: None if pd.isna(v) or v == "" else v)
    return df


def upsert_lookup(conn, table: str, column: str, values: list[str]) -> dict[str, int]:
    """Insère les valeurs uniques d'une table de référence (artiste/genre) et renvoie
    le mapping nom -> id, pour résoudre les clés étrangères des morceaux."""
    unique_values = sorted(set(v for v in values if v))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {table} ({column}) VALUES %s ON CONFLICT ({column}) DO NOTHING",
            [(v,) for v in unique_values],
        )
        cur.execute(f"SELECT id_{table}, {column} FROM {table}")
        mapping = {name: id_ for id_, name in cur.fetchall()}
    conn.commit()
    logger.info("Table '%s' : %d valeurs uniques importées.", table, len(unique_values))
    return mapping


def insert_tracks(conn, df: pd.DataFrame, artiste_ids: dict[str, int], genre_ids: dict[str, int]) -> int:
    rows = [
        (
            row.titre,
            int(row.duree_secondes),
            row.date_sortie,
            int(row.popularite),
            row.source,
            artiste_ids[row.artiste],
            genre_ids[row.genre],
        )
        for row in df.itertuples(index=False)
    ]

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO morceau (titre, duree_secondes, date_sortie, popularite, source, id_artiste, id_genre)
            VALUES %s
            ON CONFLICT (titre, id_artiste) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def main() -> None:
    try:
        df = load_final_dataset()
    except ImportError_ as exc:
        logger.error("Import interrompu : %s", exc)
        return

    logger.info("Jeu de données final chargé : %d lignes", len(df))

    try:
        ensure_database_exists()
    except psycopg2.Error as exc:
        logger.error("Import interrompu : connexion Postgres impossible (%s)", exc)
        return

    conn = get_target_connection()
    try:
        apply_schema(conn)

        artiste_ids = upsert_lookup(conn, "artiste", "nom", df["artiste"].tolist())
        genre_ids = upsert_lookup(conn, "genre", "nom", df["genre"].tolist())

        n_inserted = insert_tracks(conn, df, artiste_ids, genre_ids)
        logger.info("Import terminé avec succès : %d morceaux traités.", n_inserted)
    except psycopg2.Error as exc:
        logger.error("Import interrompu : %s", exc)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

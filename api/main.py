"""API REST du projet (C5) — FastAPI, CRUD sur /tracks et /artists.

Technos : FastAPI + Uvicorn, psycopg2 (pas d'ORM). Doc Swagger/OpenAPI générée
automatiquement par FastAPI (/docs, /redoc).

Choix "pas d'ORM" : mêmes raisons qu'en C2 (docs/requetes_sql.md) — peu de requêtes,
toutes simples, et le schéma est déjà défini une seule fois dans db/schema.sql ; ajouter
SQLAlchemy dupliquerait ce schéma dans des modèles Python sans bénéfice réel ici.

Auth : clé API simple, envoyée dans le header `X-API-Key`, comparée à la variable
d'environnement API_KEY. Toute requête sur /tracks ou /artists sans cette clé (ou avec une
clé invalide) est rejetée en 401. Suffisant pour la démonstration demandée (C5), pas conçu
pour de la prod (pas de rotation de clé, pas de scopes).

Lancement : uvicorn api.main:app --reload (depuis la racine du projet)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

PG_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]
PG_TARGET_DB = os.environ.get("POSTGRES_TARGET_DB", "musicdata")
API_KEY = os.environ["API_KEY"]

app = FastAPI(
    title="MusicData API",
    description="API REST sur le jeu de données musicales agrégé (projet certification RNCP E1).",
    version="1.0.0",
)


# --- Connexion DB -----------------------------------------------------------------

@contextmanager
def get_connection():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_TARGET_DB)
    try:
        yield conn
    finally:
        conn.close()


# --- Auth ---------------------------------------------------------------------------

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: Optional[str] = Security(api_key_header)) -> None:
    if key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API manquante ou invalide")


# --- Schémas Pydantic -----------------------------------------------------------------

class ArtisteIn(BaseModel):
    nom: str = Field(..., min_length=1, max_length=255)


class ArtisteOut(ArtisteIn):
    id_artiste: int


class MorceauIn(BaseModel):
    titre: str = Field(..., min_length=1)
    duree_secondes: int = Field(0, ge=0)
    date_sortie: Optional[str] = None  # format ISO YYYY-MM-DD
    popularite: int = Field(0, ge=0, le=100)
    source: str = "api"
    id_artiste: int
    id_genre: int


class MorceauOut(BaseModel):
    id_morceau: int
    titre: str
    artiste: str
    genre: str
    duree_secondes: int
    date_sortie: Optional[str]
    popularite: int
    source: str


# --- Routes : artistes ----------------------------------------------------------------

@app.get("/artists", response_model=list[ArtisteOut], dependencies=[Depends(verify_api_key)], tags=["artists"])
def list_artists(limit: int = 50, offset: int = 0):
    limit = min(limit, 500)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_artiste, nom FROM artiste ORDER BY id_artiste LIMIT %s OFFSET %s", (limit, offset))
        return [{"id_artiste": row[0], "nom": row[1]} for row in cur.fetchall()]


@app.get("/artists/{artist_id}", response_model=ArtisteOut, dependencies=[Depends(verify_api_key)], tags=["artists"])
def get_artist(artist_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_artiste, nom FROM artiste WHERE id_artiste = %s", (artist_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Artiste introuvable")
    return {"id_artiste": row[0], "nom": row[1]}


@app.post("/artists", response_model=ArtisteOut, status_code=201, dependencies=[Depends(verify_api_key)], tags=["artists"])
def create_artist(artist: ArtisteIn):
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO artiste (nom) VALUES (%s) RETURNING id_artiste", (artist.nom,))
        except psycopg2.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="Un artiste avec ce nom existe déjà")
        artist_id = cur.fetchone()[0]
        conn.commit()
    return {"id_artiste": artist_id, "nom": artist.nom}


@app.put("/artists/{artist_id}", response_model=ArtisteOut, dependencies=[Depends(verify_api_key)], tags=["artists"])
def update_artist(artist_id: int, artist: ArtisteIn):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE artiste SET nom = %s WHERE id_artiste = %s RETURNING id_artiste", (artist.nom, artist_id))
        row = cur.fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Artiste introuvable")
    return {"id_artiste": artist_id, "nom": artist.nom}


@app.delete("/artists/{artist_id}", status_code=204, dependencies=[Depends(verify_api_key)], tags=["artists"])
def delete_artist(artist_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute("DELETE FROM artiste WHERE id_artiste = %s RETURNING id_artiste", (artist_id,))
        except psycopg2.errors.ForeignKeyViolation:
            raise HTTPException(status_code=409, detail="Impossible de supprimer : des morceaux référencent cet artiste")
        row = cur.fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Artiste introuvable")


# --- Routes : morceaux ------------------------------------------------------------------

TRACK_SELECT = """
    SELECT m.id_morceau, m.titre, a.nom, g.nom, m.duree_secondes, m.date_sortie, m.popularite, m.source
    FROM morceau m
    JOIN artiste a ON a.id_artiste = m.id_artiste
    JOIN genre g ON g.id_genre = m.id_genre
"""


def _row_to_track(row) -> dict:
    return {
        "id_morceau": row[0],
        "titre": row[1],
        "artiste": row[2],
        "genre": row[3],
        "duree_secondes": row[4],
        "date_sortie": row[5].isoformat() if row[5] else None,
        "popularite": row[6],
        "source": row[7],
    }


@app.get("/tracks", response_model=list[MorceauOut], dependencies=[Depends(verify_api_key)], tags=["tracks"])
def list_tracks(limit: int = 50, offset: int = 0):
    limit = min(limit, 500)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"{TRACK_SELECT} ORDER BY m.id_morceau LIMIT %s OFFSET %s", (limit, offset))
        return [_row_to_track(row) for row in cur.fetchall()]


@app.get("/tracks/{track_id}", response_model=MorceauOut, dependencies=[Depends(verify_api_key)], tags=["tracks"])
def get_track(track_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"{TRACK_SELECT} WHERE m.id_morceau = %s", (track_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Morceau introuvable")
    return _row_to_track(row)


@app.post("/tracks", response_model=MorceauOut, status_code=201, dependencies=[Depends(verify_api_key)], tags=["tracks"])
def create_track(track: MorceauIn):
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO morceau (titre, duree_secondes, date_sortie, popularite, source, id_artiste, id_genre)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id_morceau
                """,
                (track.titre, track.duree_secondes, track.date_sortie, track.popularite, track.source, track.id_artiste, track.id_genre),
            )
        except psycopg2.errors.ForeignKeyViolation:
            raise HTTPException(status_code=400, detail="id_artiste ou id_genre inconnu")
        except psycopg2.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="Ce morceau existe déjà pour cet artiste")
        track_id = cur.fetchone()[0]
        conn.commit()
        cur.execute(f"{TRACK_SELECT} WHERE m.id_morceau = %s", (track_id,))
        return _row_to_track(cur.fetchone())


@app.put("/tracks/{track_id}", response_model=MorceauOut, dependencies=[Depends(verify_api_key)], tags=["tracks"])
def update_track(track_id: int, track: MorceauIn):
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                """
                UPDATE morceau
                SET titre = %s, duree_secondes = %s, date_sortie = %s, popularite = %s,
                    source = %s, id_artiste = %s, id_genre = %s
                WHERE id_morceau = %s
                RETURNING id_morceau
                """,
                (track.titre, track.duree_secondes, track.date_sortie, track.popularite, track.source, track.id_artiste, track.id_genre, track_id),
            )
        except psycopg2.errors.ForeignKeyViolation:
            raise HTTPException(status_code=400, detail="id_artiste ou id_genre inconnu")
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise HTTPException(status_code=404, detail="Morceau introuvable")
        cur.execute(f"{TRACK_SELECT} WHERE m.id_morceau = %s", (track_id,))
        return _row_to_track(cur.fetchone())


@app.delete("/tracks/{track_id}", status_code=204, dependencies=[Depends(verify_api_key)], tags=["tracks"])
def delete_track(track_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM morceau WHERE id_morceau = %s RETURNING id_morceau", (track_id,))
        row = cur.fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Morceau introuvable")


# --- Santé (public, pas d'auth) -----------------------------------------------------

@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "docs": "/docs"}

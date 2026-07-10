"""Peuple la base Postgres "source" avec un échantillon de données MusicBrainz.

Ce script n'est PAS l'un des 5 scripts d'extraction du projet : il simule
l'existence préalable d'une base SQL métier déjà remplie, que extract/db_query.py
vient ensuite interroger en lecture seule (cas réel : on n'a pas la main sur le
peuplement d'une base source externe).

API MusicBrainz (publique, sans authentification) : https://musicbrainz.org/ws/2/
Quota respecté : ~1 requête/seconde, User-Agent descriptif (obligatoire par leurs CGU).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MB_BASE_URL = "https://musicbrainz.org/ws/2"
MB_HEADERS = {"User-Agent": "musicdata-project/1.0 (projet certification RNCP; contact: sonicario49@gmail.com)"}
REQUEST_TIMEOUT = 10
RATE_LIMIT_DELAY = 1.1  # secondes, quota MusicBrainz ~1 req/s

ARTIST_NAMES = [
    "Daft Punk", "Beyoncé", "Adele", "Metallica", "Miles Davis",
    "Bob Marley", "Ed Sheeran", "The Beatles", "Kendrick Lamar", "Billie Eilish",
    "Coldplay", "David Bowie", "Radiohead", "Aya Nakamura", "Stromae",
]
ALBUMS_PER_ARTIST = 2
TRACKS_PER_ALBUM = 8


class SeedError(Exception):
    """Levée quand un appel MusicBrainz échoue de façon non récupérable."""


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def mb_get(path: str, params: dict) -> dict:
    time.sleep(RATE_LIMIT_DELAY)
    try:
        response = requests.get(f"{MB_BASE_URL}{path}", params=params, headers=MB_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise SeedError(f"Échec de la requête MusicBrainz {path} : {exc}") from exc
    return response.json()


def create_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS artists (
                id SERIAL PRIMARY KEY,
                mbid UUID UNIQUE NOT NULL,
                name TEXT NOT NULL,
                genre TEXT
            );
            CREATE TABLE IF NOT EXISTS albums (
                id SERIAL PRIMARY KEY,
                mbid UUID UNIQUE NOT NULL,
                artist_id INTEGER NOT NULL REFERENCES artists(id),
                title TEXT NOT NULL,
                release_date TEXT
            );
            CREATE TABLE IF NOT EXISTS tracks (
                id SERIAL PRIMARY KEY,
                mbid UUID UNIQUE,
                album_id INTEGER NOT NULL REFERENCES albums(id),
                title TEXT NOT NULL,
                duration_ms INTEGER
            );

            -- Postgres n'indexe pas automatiquement les colonnes de clé étrangère
            -- (seule la PK référencée l'est) : sans ça, toute requête qui remonte
            -- d'un artiste vers ses morceaux (artist_id puis album_id) force un
            -- Seq Scan complet sur albums/tracks. Cf. docs/requetes_sql.md pour
            -- la comparaison EXPLAIN ANALYZE avant/après.
            CREATE INDEX IF NOT EXISTS idx_albums_artist_id ON albums(artist_id);
            CREATE INDEX IF NOT EXISTS idx_tracks_album_id ON tracks(album_id);
        """)
    conn.commit()
    logger.info("Schéma source (artists/albums/tracks) prêt.")


def fetch_artist(name: str) -> dict | None:
    data = mb_get("/artist/", {"query": f'artist:"{name}"', "fmt": "json", "limit": 1})
    artists = data.get("artists", [])
    return artists[0] if artists else None


def fetch_albums(artist_mbid: str, limit: int) -> list[dict]:
    data = mb_get("/release-group", {"artist": artist_mbid, "type": "album", "fmt": "json", "limit": limit})
    return data.get("release-groups", [])


def fetch_first_release_id(release_group_mbid: str) -> str | None:
    data = mb_get("/release", {"release-group": release_group_mbid, "fmt": "json", "limit": 1})
    releases = data.get("releases", [])
    return releases[0]["id"] if releases else None


def fetch_tracks(release_mbid: str, limit: int) -> list[dict]:
    data = mb_get(f"/release/{release_mbid}", {"inc": "recordings", "fmt": "json"})
    tracks: list[dict] = []
    for medium in data.get("media", []):
        tracks.extend(medium.get("tracks", []))
    return tracks[:limit]


def top_tag(tags: list[dict]) -> str | None:
    if not tags:
        return None
    return max(tags, key=lambda t: t.get("count", 0))["name"]


def seed_artist(conn, name: str) -> None:
    artist = fetch_artist(name)
    if artist is None:
        logger.warning("Artiste introuvable sur MusicBrainz : %s", name)
        return

    genre = top_tag(artist.get("tags", [])) or "inconnu"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO artists (mbid, name, genre) VALUES (%s, %s, %s)
            ON CONFLICT (mbid) DO UPDATE SET genre = EXCLUDED.genre
            RETURNING id
            """,
            (artist["id"], artist["name"], genre),
        )
        artist_id = cur.fetchone()[0]
    conn.commit()

    for release_group in fetch_albums(artist["id"], ALBUMS_PER_ARTIST):
        release_id = fetch_first_release_id(release_group["id"])
        if release_id is None:
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO albums (mbid, artist_id, title, release_date) VALUES (%s, %s, %s, %s)
                ON CONFLICT (mbid) DO UPDATE SET title = EXCLUDED.title
                RETURNING id
                """,
                (release_group["id"], artist_id, release_group["title"], release_group.get("first-release-date", "")),
            )
            album_id = cur.fetchone()[0]
        conn.commit()

        tracks = fetch_tracks(release_id, TRACKS_PER_ALBUM)
        with conn.cursor() as cur:
            for track in tracks:
                recording = track.get("recording", {})
                cur.execute(
                    """
                    INSERT INTO tracks (mbid, album_id, title, duration_ms) VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (recording.get("id"), album_id, track.get("title", recording.get("title", "")), track.get("length")),
                )
        conn.commit()
        logger.info("Album '%s' (%s) : %d morceaux insérés", release_group["title"], artist["name"], len(tracks))


def main() -> None:
    conn = get_connection()
    try:
        create_schema(conn)
        for name in ARTIST_NAMES:
            try:
                seed_artist(conn, name)
            except SeedError as exc:
                logger.warning("Artiste '%s' ignoré : %s", name, exc)
                continue
        logger.info("Peuplement de la base source terminé.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

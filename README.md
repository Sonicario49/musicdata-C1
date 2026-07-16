# MusicData

Pipeline de collecte, harmonisation et mise à disposition de données musicales, à partir
de 5 sources hétérogènes (API, scraping, fichier, base SQL, Big Data), agrégées en un
jeu de données unique, stockées dans PostgreSQL, et exposées via une API REST.

Chaque extraction sauvegarde uniquement la donnée brute, dans le format natif de sa
source (JSON, HTML, CSV natif, Parquet natif) : le nettoyage et l'harmonisation vers le
schéma commun (`titre, artiste, genre, durée, date de sortie, popularité`) sont entièrement
faits à l'étape d'agrégation (C3), pas à l'extraction.

## Stack technique

- **Python 3.10**
- **Extraction** : `requests`, `BeautifulSoup4`, `pandas`, `psycopg2`, `duckdb`
- **Stockage** : PostgreSQL 16 (via Docker Compose)
- **Agrégation** : pandas
- **API** : FastAPI + Uvicorn
- **Sources externes** : API Deezer, API MusicBrainz, kworb.net, datasets Kaggle

## Structure du projet

```
extract/            scripts d'extraction, un par source (raw uniquement, pas de normalisation)
  api_deezer.py        API Deezer (Web API) -> JSON brut
  scraping_charts.py    kworb.net (scraping) -> HTML brut
  file_csv.py           dataset Kaggle "Spotify Tracks Dataset" (fichier) -> copie CSV native
  db_query.py            requête PostgreSQL (base SQL) -> CSV aux colonnes natives
  bigdata_duckdb.py      requête DuckDB sur Parquet volumineux (Big Data) -> Parquet aux colonnes natives
aggregation/
  aggregate.py           parse les 5 formats natifs, harmonise et fusionne en un jeu final (Parquet)
db/
  schema.sql              modèle Merise (MCD/MLD) de la base cible
  seed_source_db.py       peuple la base source depuis l'API MusicBrainz
  import.py               importe le jeu final dans la base cible
api/
  main.py                 API REST FastAPI (CRUD + auth par clé API)
docs/
  tableau_sources.md      récapitulatif des 5 sources
  requetes_sql.md         requêtes SQL documentées (EXPLAIN ANALYZE, optimisation)
  rgpd.md                 volet RGPD
data/
  raw/                    sorties brutes (natives) des scripts d'extraction (ignoré par Git)
  external/                fichiers téléchargés manuellement (ignoré par Git)
  processed/               jeu de données final après agrégation, en Parquet (ignoré par Git)
```

## Installation

Prérequis : Python 3.10+, Docker Desktop.

```bash
git clone https://github.com/Sonicario49/musicdata-C1.git
cd musicdata-C1
pip install -r requirements.txt
cp .env.example .env   # puis renseigner un mot de passe et une clé API
docker compose up -d   # démarre PostgreSQL sur localhost:5432
```

Deux fichiers doivent être téléchargés manuellement avant de lancer certains scripts :

| Fichier à placer dans `data/external/` | Source |
|---|---|
| `spotify_tracks_kaggle.csv` | [Spotify Tracks Dataset](https://www.kaggle.com/datasets/maharshipandya/spotify-tracks-dataset) (compte Kaggle gratuit requis) |
| `spotify-huge-audio-features.parquet` | Spotify Huge Track Analysis Dataset (56,3M lignes, ~4.1 Go , voir `data/external/README_spotify_huge_audio_features.md`) |

## Utilisation

Lancer les étapes dans cet ordre depuis la racine du projet :

```bash
# 1. Peupler la base source (MusicBrainz) utilisée par db_query.py
python db/seed_source_db.py

# 2. Extraction des 5 sources -> data/raw/ (format natif : JSON, HTML, CSV, Parquet)
python extract/api_deezer.py
python extract/scraping_charts.py
python extract/file_csv.py
python extract/db_query.py
python extract/bigdata_duckdb.py

# 3. Agrégation des 5 sources -> data/processed/musicdata_final.parquet
python aggregation/aggregate.py

# 4. Import du jeu final dans la base cible PostgreSQL
python db/import.py

# 5. Lancer l'API (port 8010 pour éviter tout conflit avec le port 8000, souvent pris)
uvicorn api.main:app --reload --port 8010
```

L'API est alors disponible sur `http://127.0.0.1:8010`, avec la documentation Swagger
sur `/docs`. Toutes les routes `/tracks` et `/artists` nécessitent une clé API dans le
header `X-API-Key` (valeur définie dans `.env`).

## Documentation complémentaire

- [`docs/tableau_sources.md`](docs/tableau_sources.md) : détail des 5 sources (provenance, format, volume, champs)
- [`docs/requetes_sql.md`](docs/requetes_sql.md) : requêtes SQL, plans `EXPLAIN ANALYZE`, optimisations
- [`docs/rgpd.md`](docs/rgpd.md) : volet RGPD

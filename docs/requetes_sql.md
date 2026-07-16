# Requêtes SQL : C2

Ce document couvre la compétence **C2 : requêter des données en SQL, depuis une DB ou un
système de Big Data**. Les deux requêtes ci-dessous sont celles réellement exécutées par
`extract/db_query.py` (PostgreSQL) et `extract/bigdata_duckdb.py` (DuckDB) : les chiffres
et plans d'exécution reproduits ici viennent d'exécutions réelles sur les données du projet,
pas d'estimations.

---

## Requête 1 : PostgreSQL (`extract/db_query.py`)

```sql
SELECT
    tracks.title,
    artists.name AS artist_name,
    artists.genre,
    tracks.duration_ms,
    albums.release_date
FROM tracks
JOIN albums ON albums.id = tracks.album_id
JOIN artists ON artists.id = albums.artist_id
WHERE tracks.duration_ms IS NOT NULL
  AND artists.genre IS NOT NULL
  AND artists.genre <> 'inconnu'
ORDER BY artists.name, albums.release_date;
```

**Choix faits :**
- Jointure sur 3 tables (`tracks` → `albums` → `artists`) pour reconstituer une ligne
  "morceau complet" à partir du modèle relationnel normalisé (cf. `db/seed_source_db.py`).
- Filtre `duration_ms IS NOT NULL` : élimine les morceaux dont la durée est inconnue côté
  MusicBrainz (champ absent sur certains enregistrements), inutile pour le schéma cible.
- Filtre `genre <> 'inconnu'` : évite de propager la valeur de repli utilisée quand un
  artiste MusicBrainz n'a aucun tag de genre.
- Colonnes explicitement nommées (pas de `SELECT *`) : seules les colonnes utiles sont
  remontées, ce qui réduit le volume transféré et documente clairement l'intention de la
  requête. Pas d'alias vers le schéma commun du projet (`titre`, `date_sortie`...) : cette
  requête ne fait que **récupérer** la donnée relationnelle telle qu'elle est modélisée en
  base (colonnes natives) ; le renommage vers le schéma cible est fait plus tard, à
  l'agrégation (C3), pas à l'extraction.

**Résultat réel :** 116 morceaux en base → 92 lignes après filtres.

### Index et optimisation

PostgreSQL indexe automatiquement les clés primaires, **mais pas les clés étrangères**
(`albums.artist_id`, `tracks.album_id`). Sur une requête qui part d'un artiste pour
redescendre vers ses morceaux, ça force un `Seq Scan` complet sur la table intermédiaire :

```sql
EXPLAIN ANALYZE
SELECT tracks.title, tracks.duration_ms
FROM artists
JOIN albums ON albums.artist_id = artists.id
JOIN tracks ON tracks.album_id = albums.id
WHERE artists.name = 'Daft Punk';
```

| | Avant index | Après `CREATE INDEX idx_tracks_album_id ON tracks(album_id)` |
|---|---|---|
| Plan | `Nested Loop` → `Seq Scan on tracks` (116 lignes lues intégralement) + `Memoize` | `Hash Join` puis `Index Scan using idx_tracks_album_id` |
| Execution Time | **0.252 ms** | **0.127 ms** (~2x plus rapide) |

Les deux index (`idx_albums_artist_id`, `idx_tracks_album_id`) sont créés dans
`db/seed_source_db.py` (`create_schema`), donc reproductibles.

**Remarque honnête sur l'échelle :** avec seulement 13 artistes / 16 albums / 116 morceaux,
PostgreSQL choisit souvent un plan basé sur un `Seq Scan` + `Hash Join` en mémoire même
quand un index existe, car lire une petite table entière est moins cher qu'un aller-retour
d'index. Le gain observé ci-dessus est réel mais modeste ; il deviendrait nettement plus
significatif à mesure que la table `tracks` grossit (des milliers/millions de lignes), où un
`Seq Scan` devient prohibitif alors qu'un `Index Scan` reste en `O(log n)`.

### Requêtes N+1

L'extraction Deezer (`extract/api_deezer.py`) illustre un piège n+1 réel dans ce projet :
récupérer le détail de chaque album nécessite un appel API par morceau. Sur le run réel,
50 morceaux ne pointaient que vers 48 albums distincts ; le script met en cache les
réponses par `album_id` (`album_cache`) pour ne pas refaire ces 2 appels redondants. À plus
grande échelle (un chart de plusieurs milliers de titres), ce cache est ce qui évite de
transformer une extraction en autant de requêtes que de morceaux.

---

## Requête 2 : DuckDB (`extract/bigdata_duckdb.py`)

```sql
COPY (
    SELECT
        track_name,
        artist_name,
        album_release_date,
        duration_ms,
        track_popularity,
        'bigdata_duckdb' AS source
    FROM read_parquet('data/external/spotify-huge-audio-features.parquet')
    WHERE track_popularity >= 50
) TO 'data/raw/bigdata_duckdb_tracks.parquet' (FORMAT PARQUET)
```

Source : "Spotify Huge Track Analysis Dataset" (Hugging Face), **56 277 664 lignes**, 27
colonnes, ~4,1 Go en Parquet (cf. `data/external/README_spotify_huge_audio_features.md`).
C'est un vrai volume Big Data : ce fichier ne tient pas raisonnablement en mémoire via
pandas (`pd.read_csv`/`pd.read_parquet` sur la totalité), alors que DuckDB l'interroge
directement sur disque sans le matérialiser entièrement.

**Choix faits :**
- Pas de jointure ici (le Parquet est déjà à plat, contrairement à l'ancienne source à 2
  fichiers CSV) : la démonstration Big Data porte sur le **filtrage par predicate pushdown**
  sur un volume que pandas ne peut pas charger tel quel.
- Colonnes explicitement listées, pas de `SELECT *` : seules 5 colonnes sur 27 sont lues,
  ce qui réduit d'autant les données réellement décompressées depuis le Parquet.
- Aucun alias vers le schéma commun (`titre`, `duree_secondes`...) : cette requête ne fait
  que filtrer/projeter la donnée native ; l'harmonisation est faite à l'agrégation (C3).

**Résultat réel :** 308 736 lignes (popularité ≥ 50) extraites des 56 277 664 lignes source,
en **~1.8 secondes** (script complet, connexion DuckDB comprise).

### EXPLAIN et optimisation

```
con.execute("EXPLAIN " + requete)
```

Le plan réel (`EXPLAIN`) montre un unique `TABLE_SCAN` sur `READ_PARQUET` avec, au niveau du
scan lui-même :
- **`Projections`** : seules les 5 colonnes utiles sont listées (pas les 22 autres, dont les
  8 colonnes d'audio features type `danceability`/`energy`/`tempo`) , DuckDB ne décompresse
  que les column chunks nécessaires.
- **`Filters: track_popularity>=50`** appliqué **dans le scan lui-même**, pas dans un nœud
  `FILTER` séparé en aval : c'est le *predicate pushdown* jusqu'au reader Parquet.

**Constat mesuré :** un simple `SELECT count(*) ... WHERE track_popularity >= 50` (sans
même projeter les autres colonnes) s'exécute en **~46 ms**. Le Parquet est organisé en 57
row groups, chacun avec des statistiques min/max par colonne ; DuckDB élimine directement
les row groups dont le maximum de `track_popularity` est < 50 sans même les lire, et ne
décompresse que ceux qui peuvent contenir des lignes valides. C'est ce mécanisme (row group
pruning via les statistiques Parquet) qui rend une requête filtrante sur 56M lignes quasi
instantanée , impossible à obtenir avec un CSV brut, qui n'a pas ce genre de métadonnées et
doit être lu ligne par ligne.

---

## ORM

Ce projet n'utilise pas d'ORM pour les scripts d'extraction : les requêtes sont écrites en
SQL brut via `psycopg2` (Postgres) et l'API Python de `duckdb`. Pour un petit nombre de
requêtes analytiques bien ciblées comme celles-ci, le SQL brut donne une visibilité directe
sur la requête réellement exécutée et sur son plan (`EXPLAIN`), ce qu'un ORM a tendance à
masquer , et c'est précisément cette visibilité qui est évaluée par cette compétence. Un ORM
(ex: SQLAlchemy) sera envisagé pour l'API REST (C5, FastAPI) où les opérations CRUD
simples sur la base finale bénéficient davantage de sa productivité que de la visibilité
fine sur chaque requête.

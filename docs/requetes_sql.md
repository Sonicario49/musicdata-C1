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
    tracks.title AS titre,
    artists.name AS artiste,
    artists.genre AS genre,
    tracks.duration_ms AS duree_ms,
    albums.release_date AS date_sortie
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
- Colonnes explicitement nommées (pas de `SELECT *`) : seules les colonnes utiles au
  schéma commun du projet sont remontées, ce qui réduit le volume transféré et documente
  clairement l'intention de la requête.

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
WITH parsed_tracks AS (
    SELECT
        name AS titre,
        regexp_extract(artists, '''([^'']*)''', 1) AS artiste,
        regexp_extract(id_artists, '''([^'']*)''', 1) AS artist_id,
        duration_ms, release_date, popularity
    FROM read_csv_auto('data/external/tracks.csv')
    WHERE duration_ms > 0 AND popularity >= 50
),
parsed_artists AS (
    SELECT id, regexp_extract(genres, '''([^'']*)''', 1) AS genre
    FROM read_csv_auto('data/external/artists.csv')
)
SELECT
    t.titre, t.artiste,
    COALESCE(NULLIF(a.genre, ''), 'inconnu') AS genre,
    (t.duration_ms // 1000) AS duree_secondes,
    t.release_date AS date_sortie,
    t.popularity AS popularite
FROM parsed_tracks t
LEFT JOIN parsed_artists a ON a.id = t.artist_id
ORDER BY t.popularity DESC;
```

**Choix faits :**
- Filtre + jointure + conditions sur deux fichiers CSV bruts (586 672 pistes × 1 162 095
  artistes), sans passage préalable par pandas : c'est DuckDB qui lit, filtre et joint.
- `WHERE duration_ms > 0 AND popularity >= 50` **avant** la jointure : ramène le côté gauche
  de 586 672 à ~223 000 lignes avant de le confronter à la table `artists` (1,16M lignes).
  C'est l'exemple concret de la "grosse jointure à éviter" : joindre les 586k pistes brutes
  contre 1,16M artistes puis filtrer après coup gaspillerait du travail de jointure sur des
  lignes qui seraient de toute façon jetées.
- Colonnes explicitement listées, pas de `SELECT *`.

**Résultat réel :** 75 843 morceaux (popularité ≥ 50) en **~0.4 seconde**.

### EXPLAIN et optimisation

```
con.execute("EXPLAIN " + requete)
```

Le plan réel (`EXPLAIN`) montre que DuckDB choisit un **`HASH_JOIN`** (adapté à une
jointure d'égalité sur de gros volumes) et applique un **filtre + une projection des
colonnes utiles dès la lecture du CSV** (`READ_CSV_AUTO` → `FILTER` → `PROJECTION`), avant
même d'atteindre la jointure. Concrètement, la table `tracks` passe de ~1,1M lignes lues à
~223 000 lignes après filtre, *avant* le hash join.

**Constat honnête :** en réécrivant la même requête avec le filtre placé *après* la
jointure plutôt qu'avant (dans la clause `WHERE` finale au lieu du CTE), le temps mesuré ne
change quasiment pas (0.43s vs 0.40s sur nos données) : l'optimiseur de DuckDB fait du
*predicate pushdown* automatique et replace le filtre au bon endroit, quel que soit l'ordre
d'écriture du SQL. On garde quand même le filtre explicite en amont dans le CTE : ça
documente l'intention pour un·e lecteur·rice humain·e, et ça reste une bonne pratique de
portabilité vers un moteur qui n'optimiserait pas aussi bien (tous ne font pas de pushdown
automatique).

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

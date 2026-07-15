-- Modélisation Merise (MCD/MLD) du jeu de données final du projet.
--
-- Choix de DB : PostgreSQL (relationnel). Justification brève : les données finales sont
-- tabulaires et structurées (un schéma fixe titre/artiste/genre/durée/date/popularité),
-- avec des relations simples et stables (un morceau a un seul artiste principal, un seul
-- genre), un modèle relationnel classique convient mieux qu'une DB documents/NoSQL ici,
-- et Postgres est déjà utilisé ailleurs dans le projet (source SQL de C1/C2).
--
-- MCD (résumé) :
--   ARTISTE (id_artiste, nom)
--   GENRE   (id_genre, nom)
--   MORCEAU (id_morceau, titre, duree_secondes, date_sortie, popularite, source)
--   MORCEAU  --(n,1)--  ARTISTE   : un morceau a un artiste, un artiste a plusieurs morceaux
--   MORCEAU  --(n,1)--  GENRE     : un morceau a un genre,   un genre a plusieurs morceaux
--
-- Pas d'entité Album : le schéma commun du projet (issu de l'agrégation C3) ne contient
-- pas de titre d'album, seulement date de sortie au niveau du morceau. Ajouter une
-- entité Album synthétique sans vraie donnée de titre n'aurait pas de valeur ajoutée ici.
--
-- MLD : voir les CREATE TABLE ci-dessous (clés primaires SERIAL, clés étrangères explicites).

CREATE TABLE IF NOT EXISTS artiste (
    id_artiste SERIAL PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS genre (
    id_genre SERIAL PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS morceau (
    id_morceau SERIAL PRIMARY KEY,
    titre TEXT NOT NULL,
    duree_secondes INTEGER NOT NULL DEFAULT 0,
    date_sortie DATE,
    popularite INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    id_artiste INTEGER NOT NULL REFERENCES artiste(id_artiste),
    id_genre INTEGER NOT NULL REFERENCES genre(id_genre),
    UNIQUE (titre, id_artiste)
);

-- Index sur les clés étrangères : Postgres ne les crée pas automatiquement
-- (cf. docs/requetes_sql.md pour la démonstration EXPLAIN ANALYZE sur ce point).
CREATE INDEX IF NOT EXISTS idx_morceau_id_artiste ON morceau(id_artiste);
CREATE INDEX IF NOT EXISTS idx_morceau_id_genre ON morceau(id_genre);

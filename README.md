# Projet Musique — Bloc E1 (Certification RNCP Développeur.se en IA)

## Contexte pour Claude Code

Ce projet a pour but de valider le **Bloc de compétences 1 : Réaliser la collecte, le stockage et la mise à disposition des données** (RNCP 37827 — Développeur.se en Intelligence Artificielle, organisme Simplon).

Il sera évalué via une épreuve **E1** qui couvre 5 compétences (C1 à C5). Le livrable attendu est :
- un **rapport professionnel** (contexte, choix techniques, difficultés) — rédigé par le candidat, pas par toi
- un **code fonctionnel et versionné sur Git**, que le jury peut consulter avant la soutenance

**Ton rôle (Claude Code) : m'aider à construire le code du projet, étape par étape, en respectant strictement les critères d'évaluation ci-dessous.** Ne saute aucune étape même si elle semble optionnelle : chaque item correspond à un critère noté "Acquis / Non acquis" par le jury.

### Thème du projet
**La musique.** Toutes les données collectées doivent converger vers un même schéma final :
`titre, artiste, genre, durée, date de sortie, popularité`

### Contrainte fondamentale
Le projet doit intégrer **5 sources de données différentes**, une de chaque type :
1. **Web API** (ex: API Deezer, pas d'auth complexe requise)
2. **Web scraping** (ex: une page de classement/charts)
3. **Fichier** (CSV/JSON, ex: dataset Kaggle "Spotify Tracks Dataset")
4. **Base de données SQL** (Postgres, remplie avec des données musique — ex: extrait MusicBrainz)
5. **Système Big Data** (DuckDB, sur un fichier volumineux)

Peu importe si une source n'est finalement pas utilisée dans l'agrégation finale : l'important est de prouver la maîtrise technique de chaque type d'accès aux données.

---

## Statut

**Projet complet : C1 à C5 implémentés, testés sur données réelles, versionnés et poussés
sur GitHub.** Voir [resumer.txt](resumer.txt) pour un bilan détaillé compétence par
compétence (chiffres réels, choix techniques justifiés, points d'attention à défendre à
l'oral). Repo : https://github.com/Sonicario49/musicdata-C1

---

## Arborescence réelle

```
musicdata-C1/
├── extract/
│   ├── api_deezer.py        # C1 - Web API (Deezer)
│   ├── scraping_charts.py   # C1 - scraping (kworb.net)
│   ├── file_csv.py          # C1 - fichier (Kaggle CSV)
│   ├── db_query.py          # C1/C2 - requête SQL (Postgres)
│   └── bigdata_duckdb.py    # C1/C2 - Big Data (DuckDB)
├── aggregation/
│   └── aggregate.py         # C3 - agrégation + harmonisation des 5 sources
├── db/
│   ├── schema.sql           # C4 - MCD/MLD, tables + FK + index
│   ├── seed_source_db.py    # peuple la DB source (MusicBrainz) pour db_query.py
│   └── import.py            # C4 - import du jeu final dans Postgres
├── api/
│   └── main.py              # C5 - API FastAPI, CRUD + auth par clé API
├── docs/
│   ├── tableau_sources.md   # C1 - récap des 5 sources
│   ├── requetes_sql.md      # C2 - requêtes SQL documentées + EXPLAIN ANALYZE
│   └── rgpd.md              # C4 - paragraphe RGPD
├── data/
│   ├── raw/          # données brutes normalisées par les scripts d'extraction (gitignored)
│   ├── external/     # fichiers téléchargés manuellement (Kaggle, gitignored)
│   └── processed/    # jeu de données final après agrégation (gitignored)
├── docker-compose.yml  # Postgres local (source + cible)
├── .env.example        # gabarit des variables d'environnement (credentials, clé API)
├── requirements.txt
├── resumer.txt          # bilan détaillé du projet, compétence par compétence
└── README.md
```

---

## Plan d'action détaillé

### Étape 0 — Setup
- [x] Initialiser le repo Git (`git init`, `.gitignore` pour `venv/`, `.env`, `data/raw/*`)
- [x] Créer l'environnement virtuel Python + `requirements.txt`
- [x] Créer l'arborescence ci-dessus

### Étape 1 — C1 : Extraction des 5 sources
Pour **chaque** script d'extraction, respecter ces points non négociables :
- [x] Point de lancement clair (`if __name__ == "__main__":`)
- [x] Initialisation des dépendances / connexions externes
- [x] Règles logiques de traitement explicites
- [x] Gestion des erreurs et exceptions (try/except, même minimal)
- [x] Sauvegarde des résultats en local (`data/raw/`) à la fin du script
- [x] Script testé et fonctionnel : toutes les données visées sont bien récupérées

Détail par source :
- [x] `api_deezer.py` : requête à l'API Deezer, récupération de morceaux/artistes (50 morceaux)
- [x] `scraping_charts.py` : scraping d'une page de charts avec `requests` + `BeautifulSoup` (kworb.net, 200 morceaux)
- [x] `file_csv.py` : lecture/nettoyage d'un CSV (Kaggle) avec `pandas` (114 000 → 81 343 lignes)
- [x] `db_query.py` : connexion à une DB Postgres, requêtes d'extraction (jointure 3 tables, 92 morceaux)
- [x] `bigdata_duckdb.py` : requêtage d'un fichier volumineux via DuckDB (586k + 1,16M lignes, 75 843 morceaux)
- [x] Rédiger `docs/tableau_sources.md` : tableau récapitulatif des 5 sources (source / provenance / type de données / format / techno / volume / champs)
- [x] Pour le scraping : garder un screenshot de la page ciblée (pour le rapport, pas pour le code) — **à faire manuellement, hors périmètre du code**

### Étape 2 — C2 : Requêtes SQL
- [x] Au moins 2 requêtes SQL fonctionnelles (sur Postgres et/ou DuckDB)
- [x] Au moins 1 requête complexe : filtre + condition + jointure
- [x] Éviter `SELECT *`
- [x] Documenter les choix (sélections, filtrages, jointures) en fonction des objectifs de collecte
- [x] Montrer une notion d'optimisation : `EXPLAIN` / `EXPLAIN ANALYZE`, discussion d'un index pertinent
- [x] Documenter ces requêtes (dans un fichier `.sql` commenté ou `docs/`) → `docs/requetes_sql.md`

### Étape 3 — C3 : Agrégation
- [x] Script `aggregation/aggregate.py` qui :
  - [x] fusionne au moins 2 sources (concaténation pandas des 5 sources)
  - [x] harmonise les formats (durée en secondes partout, genre en minuscules, dates en ISO, popularité normalisée 0-100 par source)
  - [x] supprime les entrées corrompues/doublons (517 corrompues + 16 278 doublons supprimés)
  - [x] produit **un seul jeu de données final** dans `data/processed/` (140 733 lignes)
- [x] Documenter le script : dépendances, commandes d'exécution, logique/ordre de traitement
- [x] Pandas plutôt que SQL : justifié dans le docstring du script

### Étape 4 — C4 : Modélisation & stockage DB
- [x] Modéliser en Merise (MCD/MLD) : entités `Artiste`, `Morceau`, `Genre` (pas d'`Album`, absent du jeu final — justifié dans `db/schema.sql`), avec clés primaires/étrangères
- [x] Choisir une DB relationnelle (Postgres) et justifier brièvement ce choix
- [x] `db/schema.sql` : script de création des tables, fonctionnel sans erreur
- [x] `db/import.py` : script d'import du jeu de données final dans la DB, fonctionnel (44 305 artistes, 1 873 genres, 140 733 morceaux, idempotent)
- [x] Documenter : dépendances, commandes d'exécution
- [x] RGPD : `docs/rgpd.md` (pas de données perso, mention de ce qui serait fait sinon)

### Étape 5 — C5 : API REST sécurisée
- [x] Construire l'API avec **FastAPI**
- [x] Routes CRUD complètes pour chaque ressource principale (au moins `tracks` et `artists`) :
  - [x] `GET /tracks`, `GET /tracks/{id}`, `POST /tracks`, `PUT /tracks/{id}`, `DELETE /tracks/{id}`
  - [x] idem pour `/artists`
- [x] Documentation Swagger/OpenAPI générée automatiquement (native à FastAPI)
- [x] Ajouter une authentification simple (API key en header) — testé : 401 sans clé, 200 avec la bonne clé

### Étape 6 — Finalisation
- [x] Vérifier que **tous** les scripts sont versionnés et poussés sur un dépôt Git distant (GitHub) → https://github.com/Sonicario49/musicdata-C1
- [x] Vérifier qu'aucun secret (clé API, mot de passe DB) n'est commité — utiliser `.env` + `.gitignore`
- [x] Relire chaque script : gestion d'erreurs présente ? documentation présente ?
- [x] Préparer les éléments que je réutiliserai dans mon rapport (captures d'écran, exemples de sorties, tableau récap) — **matière brute disponible dans `resumer.txt` et `docs/`, mise en forme finale à faire par le candidat**

---

## Ce que Claude Code NE doit PAS faire
- Ne pas rédiger le rapport professionnel à ma place (c'est un livrable individuel évalué par soutenance orale — je dois être capable de tout expliquer)
- Ne pas choisir MongoDB pour la source Big Data sauf si je le demande explicitement et qu'on documente pourquoi (le prof déconseille ce choix, MongoDB ne répondant pas vraiment aux 3V)
- Ne pas sur-complexifier : viser un script fonctionnel et propre plutôt qu'une architecture élaborée — la valeur ajoutée de C4 par exemple est volontairement faible

## Prochaine étape suggérée
Le code est terminé (C1 à C5). Reste : le screenshot de la page scrapée, et la rédaction
du rapport professionnel + la préparation de la soutenance orale (hors périmètre de
Claude Code) — voir [resumer.txt](resumer.txt) pour la matière brute à réutiliser.

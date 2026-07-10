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

## Arborescence cible

```
musicdata-project/
├── extract/
│   ├── api_deezer.py
│   ├── scraping_charts.py
│   ├── file_csv.py
│   ├── db_query.py
│   └── bigdata_duckdb.py
├── aggregation/
│   └── aggregate.py
├── db/
│   ├── schema.sql
│   └── import.py
├── api/
│   └── main.py
├── docs/
│   └── tableau_sources.md
├── data/
│   ├── raw/          # données brutes sauvegardées par les scripts d'extraction
│   └── processed/    # jeu de données final après agrégation
├── requirements.txt
└── README.md
```

---

## Plan d'action détaillé

### Étape 0 — Setup
- [ ] Initialiser le repo Git (`git init`, `.gitignore` pour `venv/`, `.env`, `data/raw/*`)
- [ ] Créer l'environnement virtuel Python + `requirements.txt`
- [ ] Créer l'arborescence ci-dessus

### Étape 1 — C1 : Extraction des 5 sources
Pour **chaque** script d'extraction, respecter ces points non négociables :
- [ ] Point de lancement clair (`if __name__ == "__main__":`)
- [ ] Initialisation des dépendances / connexions externes
- [ ] Règles logiques de traitement explicites
- [ ] Gestion des erreurs et exceptions (try/except, même minimal)
- [ ] Sauvegarde des résultats en local (`data/raw/`) à la fin du script
- [ ] Script testé et fonctionnel : toutes les données visées sont bien récupérées

Détail par source :
- [ ] `api_deezer.py` : requête à l'API Deezer, récupération de morceaux/artistes
- [ ] `scraping_charts.py` : scraping d'une page de charts avec `requests` + `BeautifulSoup`
- [ ] `file_csv.py` : lecture/nettoyage d'un CSV (Kaggle) avec `pandas`
- [ ] `db_query.py` : connexion à une DB Postgres, requêtes d'extraction
- [ ] `bigdata_duckdb.py` : requêtage d'un fichier volumineux via DuckDB
- [ ] Rédiger `docs/tableau_sources.md` : tableau récapitulatif des 5 sources (source / provenance / type de données / format / techno / volume / champs)
- [ ] Pour le scraping : garder un screenshot de la page ciblée (pour le rapport, pas pour le code)

### Étape 2 — C2 : Requêtes SQL
- [ ] Au moins 2 requêtes SQL fonctionnelles (sur Postgres et/ou DuckDB)
- [ ] Au moins 1 requête complexe : filtre + condition + jointure
- [ ] Éviter `SELECT *`
- [ ] Documenter les choix (sélections, filtrages, jointures) en fonction des objectifs de collecte
- [ ] Montrer une notion d'optimisation : `EXPLAIN` / `EXPLAIN ANALYZE`, discussion d'un index pertinent
- [ ] Documenter ces requêtes (dans un fichier `.sql` commenté ou `docs/`)

### Étape 3 — C3 : Agrégation
- [ ] Script `aggregation/aggregate.py` qui :
  - [ ] fusionne au moins 2 sources (JOIN SQL ou concaténation pandas)
  - [ ] harmonise les formats (ex: durée en secondes partout, genre en minuscules, dates en ISO)
  - [ ] supprime les entrées corrompues/doublons
  - [ ] produit **un seul jeu de données final** dans `data/processed/`
- [ ] Documenter le script : dépendances, commandes d'exécution, logique/ordre de traitement
- [ ] Si pandas plutôt que SQL : justifier brièvement ce choix dans la doc

### Étape 4 — C4 : Modélisation & stockage DB
- [ ] Modéliser en Merise (MCD/MLD) : entités type `Artiste`, `Album`, `Morceau`, `Genre`, avec clés primaires/étrangères
- [ ] Choisir une DB relationnelle (Postgres) et justifier brièvement ce choix
- [ ] `db/schema.sql` : script de création des tables, fonctionnel sans erreur
- [ ] `db/import.py` : script d'import du jeu de données final dans la DB, fonctionnel
- [ ] Documenter : dépendances, commandes d'exécution
- [ ] RGPD : rédiger un court paragraphe (pas de données perso ici → le mentionner brièvement + dire ce qui serait fait s'il y en avait : registre des traitements, procédure de tri)

### Étape 5 — C5 : API REST sécurisée
- [ ] Construire l'API avec **FastAPI**
- [ ] Routes CRUD complètes pour chaque ressource principale (au moins `tracks` et `artists`) :
  - [ ] `GET /tracks`, `GET /tracks/{id}`, `POST /tracks`, `PUT /tracks/{id}`, `DELETE /tracks/{id}`
  - [ ] idem pour `/artists`
- [ ] Documentation Swagger/OpenAPI générée automatiquement (native à FastAPI)
- [ ] Ajouter une authentification simple (API key en header, ou JWT basique) — au moins un mécanisme qui bloque l'accès sans credentials

### Étape 6 — Finalisation
- [ ] Vérifier que **tous** les scripts sont versionnés et poussés sur un dépôt Git distant (GitHub)
- [ ] Vérifier qu'aucun secret (clé API, mot de passe DB) n'est commité — utiliser `.env` + `.gitignore`
- [ ] Relire chaque script : gestion d'erreurs présente ? documentation présente ?
- [ ] Préparer les éléments que je réutiliserai dans mon rapport (captures d'écran, exemples de sorties, tableau récap)

---

## Ce que Claude Code NE doit PAS faire
- Ne pas rédiger le rapport professionnel à ma place (c'est un livrable individuel évalué par soutenance orale — je dois être capable de tout expliquer)
- Ne pas choisir MongoDB pour la source Big Data sauf si je le demande explicitement et qu'on documente pourquoi (le prof déconseille ce choix, MongoDB ne répondant pas vraiment aux 3V)
- Ne pas sur-complexifier : viser un script fonctionnel et propre plutôt qu'une architecture élaborée — la valeur ajoutée de C4 par exemple est volontairement faible

## Prochaine étape suggérée
Commencer par l'Étape 0 (setup) puis avancer script par script dans l'ordre C1 → C2 → C3 → C4 → C5, en validant chaque item de la checklist avant de passer au suivant.

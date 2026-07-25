# Waterflow 2 — Plateforme MLOps Qualité de l'Eau

Plateforme de classification de la potabilité de l'eau destinée aux collectivités territoriales.
Exposée via une **API Flask unique** portant trois modules : données, prédiction ML et ingestion OCR.

---

## Architecture

```
waterflow/
├── api/
│   ├── app.py                     # Factory Flask + init Swagger
│   ├── models/db.py               # Modèles SQLAlchemy (RGPD)
│   ├── middleware/auth.py         # Auth clé API (clients) + Bearer (experts)
│   ├── routes/routes.py           # Toutes les routes API
│   └── services/
│       ├── ocr_service.py         # OCR.space (primaire) + Claude Vision (fallback)
│       ├── predict_service.py     # XGBoost (chargé directement depuis model_artifacts/)
│       └── monitoring_service.py  # Data drift (PSI), dégradation, alertes
├── templates/index.html           # Interface web expert
├── scripts/
│   └── init_db.py                 # Initialisation DB + données de test
├── tests/
│   ├── test_api.py                # Tests intégration complets
│   ├── test_e2e.py                # Test bout en bout : OCR → prédiction
│   ├── test_unitaires.py          # Tests unitaires (modèle)
│   ├── test_fonctionnels.py       # Tests fonctionnels (routes)
│   ├── test_non_regression.py     # Tests de non-régression
│   └── test_model_validation.py   # Validation du modèle et de ses artefacts
├── conftest.py                     # Fixtures pytest partagées
├── pytest.ini                      # Configuration pytest
├── docs/
│   ├── architecture.md            # Documentation d'architecture
│   ├── mcd.md                     # Modélisation des données (MCD/MPD, formalisme Merise)
│   ├── rgpd.md                    # Conformité RGPD détaillée
│   ├── owasp.md                   # Correspondance OWASP API Security Top 10
│   ├── test_coverage.md           # Matrice de traçabilité tests ↔ endpoints
│   ├── test_plan_modele.md        # Plan de test du modèle (parties visées, périmètre, stratégie)
│   ├── outils_test.md             # Cohérence des outils de test avec l'environnement technique
│   ├── couverture_execution.md    # Couverture mesurée + preuve d'exécution en environnement isolé
│   ├── chaine_cicd.md             # Inventaire complet des jobs, étapes et déclencheurs CI/CD
│   ├── accessibilite.md           # Accessibilité RGAA par partie prenante
│   ├── monitoring_preuve.md       # Preuve de fonctionnement de la chaîne de monitorage
│   ├── incident.md                # Procédure de gestion d'incident
│   └── user_stories.md            # User stories du projet
├── notebooks/                      # Exploration des données, entraînement du modèle
├── data/                           # Jeu de données source (water_potability.csv)
├── samples/                        # Fiches labo (exemples OCR, dont un PDF de test manuel)
├── model_artifacts/                # Modèle XGBoost + scaler + statistiques d'entraînement
├── swagger.yaml                    # Documentation OpenAPI — accessible sur /apidocs
├── main.py                         # Point d'entrée Gunicorn
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/
│   ├── ci.yml                     # CI/CD principal (tests, build)
│   └── model_ci.yml               # CI dédiée à la validation du modèle
├── RAPPORT_CONFORMITE.md          # Rapport de conformité du projet
├── requirements.txt
└── .env.example
```

Artefacts générés au runtime (bases SQLite, tracking MLflow) ne sont pas
repris ci-dessus — voir `.gitignore`.

Modélisation des données (MCD/MPD au formalisme Merise — entités,
associations, cardinalités, décisions de modélisation notables) :
`docs/mcd.md`.

---

## Prérequis

- Python 3.11+
- Docker & Docker Compose (pour le déploiement conteneurisé)
- Au moins une clé OCR : `OCR_SPACE_API_KEY` ou `ANTHROPIC_API_KEY`

---

## Installation et lancement

### Mode local

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd waterflow

# 2. Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env : renseigner OCR_SPACE_API_KEY et/ou ANTHROPIC_API_KEY
# Configurer EXPERT_TOKENS : login:token:role,login2:token2:role2

# 5. Initialiser la base de données avec des données de test
python scripts/init_db.py

# 6. Lancer le serveur
python main.py
# → http://localhost:8080
# → Documentation Swagger : http://localhost:8080/apidocs
```

### Mode Docker

```bash
# 1. Variables d'environnement
cp .env.example .env
# Éditer .env

# 2. Lancer via Docker Compose
docker compose up -d

# 3. Initialiser la base de données
docker compose exec waterflow2 python scripts/init_db.py

# Logs
docker compose logs -f waterflow2
```

---

## Lancer les tests

```bash
# Tous les tests
pytest tests/ -v

# Avec couverture
pytest tests/ -v --cov=api

# Test bout en bout uniquement
pytest tests/test_e2e.py -v

# Tests d'intégration
pytest tests/test_api.py -v
```

Matrice de traçabilité (quel test couvre quel endpoint, et quoi précisément) :
`docs/test_coverage.md`. Plan de test du modèle ML (partie visée, périmètre
et stratégie pour chacun des 92 tests liés au modèle, dont la distinction
entre tests sur le vrai modèle et tests avec prédiction simulée) :
`docs/test_plan_modele.md`. Cohérence des outils de test choisis
(framework, bibliothèques) avec l'environnement technique du projet :
`docs/outils_test.md`. Couverture de test mesurée (82 %, seuil CI appliqué)
et preuve d'exécution reproductible sur deux environnements indépendants
(machine de dev + conteneur Docker isolé) : `docs/couverture_execution.md`.
Inventaire complet des étapes, tâches et déclencheurs (automatiques et
manuels) des deux chaînes CI/CD : `docs/chaine_cicd.md`.

---

## Routes API

Documentation interactive complète : **`/apidocs`** (Swagger UI)

| Méthode | Route                              | Auth               | Description                       |
|---------|------------------------------------|--------------------|-----------------------------------|
| GET     | /health                            | public             | État du service                   |
| POST    | /predict                           | X-API-Key          | Prédiction directe, sans stockage |
| GET     | /me                                | X-API-Key          | Profil client                     |
| GET     | /me/prelevements                   | X-API-Key          | Mes prélèvements (paginés)        |
| GET     | /me/prelevements/`<id>`            | X-API-Key          | Détail d'un prélèvement           |
| GET     | /me/resultats                      | X-API-Key          | Mes prédictions                   |
| GET     | /me/rgpd                           | X-API-Key          | Données personnelles (RGPD)       |
| DELETE  | /me/rgpd                           | X-API-Key          | Droit à l'effacement              |
| POST    | /ingest/manual                     | X-API-Key          | Déposer mesures JSON + prédiction |
| POST    | /ingest/ocr                        | X-API-Key          | Déposer fiche labo (OCR seul)     |
| POST    | /ingest/ocr-and-predict            | X-API-Key          | OCR + prédiction (pipeline)       |
| GET     | /admin/clients                     | Bearer (tout expert) | Lister les clients              |
| POST    | /admin/clients                     | Bearer (tout expert) | Créer un client                 |
| GET     | /admin/clients/`<id>`              | Bearer (tout expert) | Détail client                   |
| PUT     | /admin/clients/`<id>`              | Bearer (tout expert) | Modifier client                 |
| POST    | /admin/clients/`<id>`/apikey       | Bearer (tout expert) | Générer/régénérer clé API       |
| GET     | /analyste/prelevements             | Bearer (analyste+) | Tous les prélèvements             |
| GET     | /analyste/prelevements/`<id>`      | Bearer (analyste+) | Détail complet (+ OCR brut)      |
| GET     | /analyste/clients/`<id>`/prelevements | Bearer (analyste+) | Prélèvements d'un client donné |
| GET     | /analyste/dashboard                | Bearer (analyste+) | KPIs agrégés                     |
| GET     | /exploitation/metrics              | Bearer (exploit)   | Métriques système                 |
| GET     | /exploitation/audit                | Bearer (exploit)   | Journal d'accès RGPD              |
| GET     | /exploitation/monitoring           | Bearer (exploit)   | Data drift, dégradation, alertes modèle |

---

## Authentification

### Clients (collectivités)
```
X-API-Key: <clé_générée_par_la_plateforme>
```
ou `?api_key=<clé>` en paramètre URL.

### Experts (analystes / exploitation)
```
Authorization: Bearer <token>
```
Les tokens sont configurés via la variable d'environnement `EXPERT_TOKENS` :
```
EXPERT_TOKENS=alice:token-alice:analyste,bob:token-bob:exploit
```
Rôles : `analyste` (dashboards, prélèvements) | `exploit` (métriques, audit + tout analyste)

---

## Variables d'environnement

| Variable            | Obligatoire | Défaut                              | Description                         |
|---------------------|-------------|-------------------------------------|-------------------------------------|
| `DATABASE_URL`      | non         | `sqlite:///waterflow2.db`           | URL SQLAlchemy (SQLite ou PostgreSQL) |
| `MODEL_PATH`        | non         | `model_artifacts/xgboost_model.json` | Modèle XGBoost, chargé directement (pas via le registre MLflow) |
| `SCALER_PATH`       | non         | `model_artifacts/robust_scaler.pkl` | Chemin vers le RobustScaler         |
| `TRAINING_STATS_PATH` | non       | `model_artifacts/training_stats.json` | Baseline utilisée par `/exploitation/monitoring` (PSI) |
| `OCR_SPACE_API_KEY` | non*        | `""`                                | Clé API OCR.space                   |
| `ANTHROPIC_API_KEY` | non*        | `""`                                | Clé Claude Vision (fallback OCR)    |
| `EXPERT_TOKENS`     | **oui**     | —                                   | `login:token:role,...`              |
| `MAX_UPLOAD_MB`     | non         | `20`                                | Taille max upload OCR (Mo)          |
| `PORT`              | non         | `8080`                              | Port d'écoute                       |
| `FLASK_ENV`         | non         | `production`                        | `development` pour le mode debug    |

\* Au moins une des deux clés OCR est requise pour les routes `/ingest/ocr*`.

---

## Comptes et clés de test

Après `python scripts/init_db.py`, trois clients sont créés (clés affichées en sortie) :

| ID client    | Dénomination                 | Statut  |
|--------------|------------------------------|---------|
| CLIENT-001   | Mairie de Marseille          | actif   |
| CLIENT-002   | Syndicat des Eaux du Var     | actif   |
| CLIENT-003   | Commune de Nice              | inactif |

Les tokens experts sont définis dans `.env` via `EXPERT_TOKENS`.

---

## Fiches labo exemples (OCR)

Le dossier `samples/` contient trois fiches :

| Fichier                          | Description                                 |
|----------------------------------|---------------------------------------------|
| `fiche_labo_exemple_1.txt`       | Fiche complète → `prediction_possible=true` |
| `fiche_labo_exemple_2_partiel.txt` | Fiche partielle → `prediction_possible=false` |
| `fiche_non_potable_test.pdf`     | Fiche PDF de test manuel (non référencée dans le code ou les tests automatisés) |

---

## Conformité RGPD

- Clés API hashées SHA-256 (jamais stockées en clair)
- IPs pseudonymisées dans les logs (dernier octet masqué)
- Table `audit_logs` immuable — journal de tous les accès
- Droit à l'effacement via `DELETE /me/rgpd`
- Conservation des logs : 12 mois glissants
- Documentation complète : `docs/rgpd.md`

---

## Sécurité — OWASP API Security Top 10

Correspondance entre les mesures de sécurité en place (authentification,
autorisation par objet/fonction, limites d'upload...) et les catégories de
l'OWASP API Security Top 10 (2023), avec les manques identifiés (rate
limiting, CORS...) : documentation complète dans `docs/owasp.md`.

---

## Accessibilité (RGAA)

Justification du choix de l'outil de restitution (interface web unique)
au regard de l'accessibilité pour toutes les parties prenantes (client,
analyste, exploitation), et vérification critère par critère avec preuve
dans le code : documentation complète dans `docs/accessibilite.md`.

---

## Monitoring du modèle

Preuve de fonctionnement de la chaîne de monitorage (`/exploitation/monitoring`) :
métriques visées (US-09) vs métriques réellement calculées et restituées
(API + UI), exécutions réelles capturées (dev, Docker), tests dédiés :
documentation complète dans `docs/monitoring_preuve.md`.

---

## Limites connues et pistes d'amélioration

- Pas de rate limiting (à ajouter au niveau du reverse proxy)
- Pas de CORS configuré (nécessaire si frontend séparé)
- La clé API est unique par client (pas de rotation multiple simultanée)
- Prometheus/Grafana non intégrés (métriques accessibles via `/exploitation/metrics`)
- Authentification expert par token statique (pas de rotation automatique)

# Waterflow — Architecture technique

> Document reconstruit à partir de l'implémentation existante pour formaliser a posteriori
> le cadre technique du projet.

## 1. Vue d'ensemble

Waterflow est une **API Flask monolithique unique** portant trois modules fonctionnels
(données, prédiction ML, ingestion OCR), plutôt qu'une architecture micro-services — choix
justifié par la taille du projet (un seul contributeur, périmètre fonctionnel maîtrisable
dans un seul déploiement) et par la simplicité opérationnelle qui en découle (un seul
conteneur à surveiller, un seul point de déploiement).

```
┌───────────────────────┐        ┌──────────────────────────────────────────┐
│   Interface web        │        │              API Flask (app.py)           │
│  templates/index.html  │◄──────►│  ┌────────────┐  ┌─────────────────────┐ │
│  (client + expert)     │  HTTP  │  │ routes.py  │  │ middleware/auth.py   │ │
└───────────────────────┘        │  │ (24 routes)│  │ clé API / Bearer     │ │
                                  │  └─────┬──────┘  └─────────────────────┘ │
┌───────────────────────┐        │        │                                  │
│  Collectivités (API)   │◄──────►│  ┌─────▼──────────────────────────────┐  │
│  intégration machine   │  HTTP  │  │            services/                │  │
└───────────────────────┘        │  │  predict_service.py  (MLflow/XGBoost)│  │
                                  │  │  ocr_service.py (OCR.space + Claude) │  │
                                  │  │  monitoring_service.py (drift PSI)   │  │
                                  │  └─────┬──────────────────────────────┘  │
                                  └────────┼──────────────────────────────────┘
                                           │
                          ┌────────────────▼─────────────────┐
                          │     models/db.py (SQLAlchemy)      │
                          │  clients · prelevements · mesures  │
                          │  predictions · audit_logs          │
                          │  request_metrics                   │
                          └────────────────┬────────────────────┘
                                           │
                          ┌────────────────▼─────────────────┐
                          │  SQLite (dev/démo) ou PostgreSQL   │
                          │  (production, via DATABASE_URL)    │
                          └─────────────────────────────────────┘
```

## 2. Composants et responsabilités

| Composant | Rôle | Dépendances |
|---|---|---|
| `api/app.py` | Factory Flask, enregistrement des blueprints, init Swagger | Flask, flasgger |
| `api/routes/routes.py` | 24 routes REST (données, prédiction, OCR, admin, analyste, exploitation) | Flask |
| `api/middleware/auth.py` | Authentification clé API (clients) + Bearer token (experts, via `EXPERT_TOKENS`) | — |
| `api/services/predict_service.py` | Chargement unique du modèle MLflow/XGBoost au démarrage, exécution de l'inférence | mlflow, joblib, numpy |
| `api/services/ocr_service.py` | Extraction des 9 mesures depuis une fiche labo scannée (OCR.space, relais Claude Vision) | requests, Anthropic SDK |
| `api/services/monitoring_service.py` | Calcul du data drift (PSI), de la confiance moyenne des prédictions, génération d'alertes | numpy |
| `api/models/db.py` | Modèles SQLAlchemy 2.0 (6 tables), conformité RGPD (hash de clé, pseudonymisation IP) | SQLAlchemy |
| `templates/index.html` | Interface web unique (vue client + vue expert), conforme RGAA | Tailwind (CDN), JS vanilla |
| `scripts/init_db.py` | Initialisation de la base + jeu de données de démonstration | — |

## 3. Flux de données

**Chaîne d'ingestion et de prédiction :**

```
Fiche labo (image/PDF)  ──►  ocr_service.py  ──►  9 mesures extraites
                                    │
                                    ▼
Mesures manuelles (JSON) ──►  validation (routes.py)
                                    │
                                    ▼
                            predict_service.py
                     (RobustScaler → XGBoost via MLflow)
                                    │
                                    ▼
                    prelevement + mesures + prediction
                         (persistés en base SQL)
                                    │
                                    ▼
                       monitoring_service.py
              (PSI vs. training_stats.json, alertes)
```

Chaque écriture en base déclenche également une entrée dans `audit_logs` (traçabilité RGPD)
et dans `request_metrics` (latence, code retour — alimente `/exploitation/metrics`).

## 4. Choix techniques et justification

| Choix | Justification |
|---|---|
| Flask (monolithe) plutôt que micro-services | Périmètre fonctionnel maîtrisable en solo ; un seul déploiement à opérer |
| SQLite en développement/démo, PostgreSQL en production (via `DATABASE_URL`) | SQLite suffit pour la démonstration et les tests CI (`sqlite:///:memory:`) ; le code est compatible PostgreSQL sans changement applicatif — seule la variable d'environnement change |
| MLflow pour le versionnement du modèle | Traçabilité de la version de modèle réellement utilisée en production (`model_version` renvoyé dans chaque réponse de prédiction) |
| OCR.space en service primaire + Claude Vision en fallback | Continuité de service si le fournisseur primaire est indisponible (cf. `docs/incident.md`) sans bloquer les dépôts clients |
| Authentification à deux niveaux (clé API / Bearer + rôles) | Sépare strictement le périmètre client (ses propres données) du périmètre expert (vue transverse), conformément au principe de minimisation RGPD |

## 5. Éco-conception

- Le modèle et le scaler sont chargés **une seule fois en mémoire** au démarrage du
  processus (`_ensure_loaded()`, pattern singleton) plutôt qu'à chaque requête, ce qui
  évite des I/O disque et un recalcul coûteux à chaque prédiction.
- Les listes paginées (`/me/prelevements`, `/analyste/prelevements`) évitent de renvoyer
  l'intégralité de l'historique à chaque appel.
- L'image Docker se base sur `python:3.11-slim` plutôt qu'une image complète, réduisant la
  taille de l'image transférée et déployée à chaque mise à jour.

## 6. Déploiement et preuve de concept

Le déploiement est conteneurisé (`Dockerfile`, utilisateur non-root, healthcheck) et
orchestré via `docker-compose.yml` (volume persistant, `restart: unless-stopped`).

Le projet a deux chaînes CI/CD distinctes :
- `.github/workflows/ci.yml` — lint + tests + couverture (seuil 75 % appliqué), puis
  construction et publication de l'image sur GHCR (uniquement sur `push`, pas sur PR), puis
  déploiement SSH avec vérification de santé via `GET /health` (uniquement sur `main`).
- `.github/workflows/model_ci.yml` — validation dédiée du modèle ML (intégrité des
  artefacts, performance vs seuils, stabilité des prédictions), déclenchée automatiquement
  quand les artefacts/notebook/données changent, ou manuellement à tout moment
  (`workflow_dispatch`).

Inventaire complet des jobs, étapes et déclencheurs des deux chaînes (y compris ceux qui
ne se déclenchent pas automatiquement, ex. pas de build/deploy sur pull request) :
`docs/chaine_cicd.md`.

La preuve de concept est l'application elle-même, fonctionnelle en environnement de
pré-production (mode Docker Compose local) : `docker compose up -d`, puis
`docker compose exec waterflow2 python scripts/init_db.py` pour peupler une base de
démonstration, accessible sur `http://localhost:8080` (interface) et
`http://localhost:8080/apidocs` (documentation API).

**Conclusion PoC** : l'architecture retenue répond au besoin exprimé (US-01 à US-10) avec
un niveau de risque technique faible — les seuls points restant à consolider avant une mise
en production à plus grande échelle sont documentés dans le backlog produit (migration
PostgreSQL, rate limiting, export Prometheus/Grafana).

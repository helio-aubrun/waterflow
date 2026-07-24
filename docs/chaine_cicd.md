# Waterflow — Chaîne CI/CD : étapes, tâches et déclencheurs

> Document de preuve : inventaire complet des deux workflows GitHub Actions
> du projet — chaque job, chaque étape, et **tous** les déclencheurs
> disponibles (automatiques et manuels), construit par lecture directe des
> fichiers `.github/workflows/*.yml` plutôt que par description approximative.
> Complète `docs/architecture.md` §6 (vue d'ensemble) et
> `docs/couverture_execution.md` (preuve d'exécution de la suite de tests).

Le projet a **deux chaînes CI/CD distinctes**, avec des déclencheurs et des
objectifs différents :

| Chaîne | Fichier | Objectif |
|---|---|---|
| CI/CD applicatif | `.github/workflows/ci.yml` | Valide le code applicatif (lint, tests, couverture), construit et déploie l'image Docker |
| CI modèle ML | `.github/workflows/model_ci.yml` | Valide spécifiquement les artefacts du modèle (intégrité, performance, stabilité), indépendamment des changements de code applicatif |

## 1. `ci.yml` — CI/CD applicatif

### 1.1 Déclencheurs

| Événement | Filtre | Effet |
|---|---|---|
| `push` | branches `main`, `develop` | Déclenche `test` → `build` (car `build` a `if: github.event_name == 'push'`) → `deploy` (si `push` sur `main` **et** que le secret `DEPLOY_HOST` est renseigné, cf. §1.3) |
| `pull_request` | vers `main` | Déclenche **seulement** `test` — `build` ne s'exécute pas (`if` restreint aux `push`), donc pas d'image publiée ni de déploiement sur une PR |

Aucun déclenchement manuel (`workflow_dispatch`) sur cette chaîne — seul `push`/`pull_request`.

### 1.2 Jobs et étapes

**Job `test`** (« Tests & Lint ») — s'exécute à chaque `push` et `pull_request` :

| # | Étape | Détail |
|---|---|---|
| 1 | `actions/checkout@v4` | Récupère le code |
| 2 | `actions/setup-python@v5` | Python 3.11, cache pip |
| 3 | Installer les dépendances | `pip install -r requirements.txt pytest pytest-cov ruff` |
| 4 | Lint (ruff) | `ruff check . --select E,F,W --ignore E501` |
| 5 | Tests unitaires + couverture | `pytest tests/ --cov=api --cov-report=term-missing --cov-report=xml --cov-fail-under=75 -v` — env : `DATABASE_URL=sqlite:///:memory:`, `SCALER_PATH=mock`, clés OCR vides. **Le job échoue si la couverture globale descend sous 75 %** |
| 6 | Upload couverture (Codecov) | `codecov/codecov-action@v4`, `if: always()` — s'exécute même si les tests échouent, pour avoir le rapport dans tous les cas |

**Job `build`** (« Build Docker image ») — `needs: test`, seulement si `github.event_name == 'push'` :

| # | Étape | Détail |
|---|---|---|
| 1 | `actions/checkout@v4` | — |
| 2 | Log in GHCR | `docker/login-action@v3`, authentification avec `GITHUB_TOKEN` |
| 3 | Métadonnées image | `docker/metadata-action@v5` — tags générés : `sha-<commit>`, `<nom-de-branche>`, et `latest` uniquement si la branche est `main` |
| 4 | Build & Push | `docker/build-push-action@v5`, avec cache GitHub Actions (`type=gha`) |

**Job `deploy`** (« Déploiement production ») — `needs: build`, seulement si `github.ref == 'refs/heads/main'` **et** `secrets.DEPLOY_HOST != ''`, environnement GitHub `production` :

| # | Étape | Détail |
|---|---|---|
| 1 | SSH deploy | `appleboy/ssh-action@v1` vers `secrets.DEPLOY_HOST` : login GHCR sur la cible, `docker pull` de l'image taggée, `docker compose pull` + `up -d --remove-orphans`, puis vérification de santé (`curl -f http://localhost:8080/health`, échec du job si la vérification échoue après un délai de 10s) |

### 1.3 Ce qui ne se déclenche jamais automatiquement

- `build`/`deploy` ne tournent **jamais** sur une pull request — seul `test` s'exécute, ce qui empêche de publier une image ou de déployer depuis une branche non fusionnée.
- `deploy` ne tourne que sur `main`, pas sur `develop` — un `push` sur `develop` valide (`test`) et construit l'image (`build`), mais ne déploie pas.
- `deploy` est **ignoré (skip), pas en échec**, tant que le secret `DEPLOY_HOST` n'est pas configuré (`Settings → Secrets and variables → Actions`) — aucun serveur de production n'est provisionné à ce stade du projet ; le job reste prêt à s'activer dès que ce secret (et `DEPLOY_USER`/`DEPLOY_SSH_KEY`) seront renseignés, sans qu'il faille modifier le workflow.

## 2. `model_ci.yml` — CI dédiée à la validation du modèle ML

### 2.1 Déclencheurs

| Événement | Filtre (`paths`) | Remarque |
|---|---|---|
| `push` | `model_artifacts/**`, `notebooks/water_xgboost.ipynb`, `tests/test_model_validation.py`, `data/water_potability*.csv` | Ne se déclenche **que** si l'un de ces chemins change — un push qui ne touche que `api/routes/routes.py` par exemple ne déclenche pas cette chaîne |
| `pull_request` | `model_artifacts/**`, `notebooks/water_xgboost.ipynb`, `tests/test_model_validation.py` | Mêmes chemins, **sans** `data/water_potability*.csv` (une PR qui ne changerait que le CSV brut, sans notebook ni artefact, ne la déclenche pas — asymétrie réelle avec `push`) |
| `workflow_dispatch` | — | **Déclenchement manuel**, disponible depuis l'onglet "Actions" de GitHub, sans condition de chemin — permet de relancer la validation du modèle à la demande même sans changement de fichier |

### 2.2 Jobs et étapes

**Job `artefacts`** (« Vérification des artefacts ») — premier job, aucune dépendance :

| # | Étape | Détail |
|---|---|---|
| 1 | `actions/checkout@v4` + `setup-python@v5` (3.11) | — |
| 2 | Installer les dépendances ML | `pip install xgboost scikit-learn joblib numpy pytest` (indépendant de `requirements.txt`, dépendances minimales pour cette validation) |
| 3 | Vérifier la présence des fichiers | Boucle sur 9 fichiers attendus (`xgboost_model.json`, `robust_scaler.pkl`, `metadata.json`, `X_val_sc.npy`, `y_val.npy`, `y_pred.npy`, `y_pred_prob.npy`, `cv_scores.npy`, `training_stats.json`) — échoue (`exit 1`) si l'un manque |
| 4 | Vérifier le chargement du modèle | Charge réellement le modèle et le scaler, vérifie `n_features_in_ == 9`, affiche le ROC-AUC des métadonnées |

**Job `performance`** (« Validation des performances ») — `needs: artefacts` :

| # | Étape | Détail |
|---|---|---|
| 1-2 | Checkout + setup Python | — |
| 3 | Installer les dépendances ML | — |
| 4 | Calculer les métriques live | Recharge modèle + données de validation, recalcule accuracy/F1/ROC-AUC/PR-AUC/precision/recall/cv_mean/cv_std, compare à `THRESHOLDS` codés en dur (accuracy≥0.60, f1≥0.45, roc_auc≥0.60, pr_auc≥0.55, cv_mean≥0.62, cv_std≤0.05) — **le job échoue** (`sys.exit(1)`) si un seuil n'est pas respecté |
| 5 | Pytest modèle | `pytest tests/test_model_validation.py -v --tb=short -k "not test_metriques_coherentes"` — exclut explicitement un test (à noter : ce test est donc **jamais exécuté en CI**, seulement en local) |
| 6 | Exporter le rapport de métriques | Génère `model_metrics_report.json` (`if: always()` — même si l'étape précédente a échoué) |
| 7 | Upload rapport métriques | `actions/upload-artifact@v4`, conservé 30 jours, `if: always()` |

**Job `stabilite`** (« Non-régression du modèle ») — `needs: artefacts` (en parallèle de `performance`, pas après) :

| # | Étape | Détail |
|---|---|---|
| 1-3 | Checkout, setup Python, dépendances | — |
| 4 | Vérifier la stabilité des prédictions | Compare les prédictions live aux prédictions sauvegardées (`y_pred.npy`/`y_pred_prob.npy`) — échoue si une classe prédite diverge ou si l'écart de probabilité dépasse `1e-4` |
| 5 | Pytest stabilité | `pytest tests/test_model_validation.py::TestStabilite -v --tb=short` |

### 2.3 Point de vigilance trouvé en construisant cet inventaire

Le job `performance` exclut `test_metriques_coherentes` (`-k "not test_metriques_coherentes"`) **sans commentaire expliquant pourquoi** dans le fichier YAML — ce test s'exécute donc uniquement lors d'un lancement local de la suite complète (`pytest tests/`), jamais en CI. Ce n'est pas nécessairement un défaut (le test peut être redondant avec les vérifications de seuils faites juste avant dans la même étape), mais ce n'était documenté nulle part avant ce document.

## 3. Comment déclencher chaque chaîne manuellement (reproduction)

```bash
# ci.yml : uniquement via push/PR, pas de déclenchement manuel possible
git push origin ma-branche   # déclenche `test` (+ `build` si push direct, pas via PR)

# model_ci.yml : déclenchement manuel possible sans toucher aux fichiers surveillés
# Onglet GitHub "Actions" → "Waterflow — CI Modèle ML" → "Run workflow"
# (équivalent CLI : gh workflow run model_ci.yml)
```

## 4. Limites

- Cet inventaire est construit par lecture statique des fichiers YAML — il ne
  constitue pas une preuve d'exécution réelle sur GitHub Actions (nécessiterait
  un push vers le remote et l'observation d'un run réel, hors périmètre de
  cette vérification documentaire).
- Les secrets requis (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`,
  `GITHUB_TOKEN` implicite) ne sont pas vérifiés ici — leur configuration
  réelle dans les paramètres du dépôt GitHub n'a pas été auditée.

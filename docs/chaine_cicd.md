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
| `push` | branches `main`, `develop` | Déclenche `test` → `build` (car `build` a `if: github.event_name == 'push'`) → `deploy` (si `push` sur `main` **et** que la variable de dépôt `DEPLOY_HOST` est renseignée, cf. §1.3) |
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

**Job `deploy`** (« Déploiement production ») — `needs: build`, seulement si `github.ref == 'refs/heads/main'` **et** `vars.DEPLOY_HOST != ''`, environnement GitHub `production` :

> Pourquoi une **variable** (`vars.DEPLOY_HOST`) et pas un secret pour cette
> condition : GitHub Actions interdit la référence à `secrets.*` dans un
> `if:` de job (`Unrecognized named-value: 'secrets'`, erreur réelle
> rencontrée en essayant `secrets.DEPLOY_HOST != ''`). Un nom d'hôte n'étant
> pas une information sensible en soi (contrairement à l'utilisateur SSH ou
> la clé privée, qui restent des secrets), `DEPLOY_HOST` est stocké comme
> variable de dépôt (`Settings → Secrets and variables → Actions →
> Variables`), ce qui permet de l'utiliser à la fois dans le `if:` du job et
> comme valeur `host:` de l'étape SSH.

| # | Étape | Détail |
|---|---|---|
| 1 | SSH deploy | `appleboy/ssh-action@v1` vers `vars.DEPLOY_HOST` (utilisateur/clé restent des secrets : `secrets.DEPLOY_USER`/`secrets.DEPLOY_SSH_KEY`) : login GHCR sur la cible, `docker pull` de l'image taggée, `docker compose pull` + `up -d --remove-orphans`, puis vérification de santé (`curl -f http://localhost:8080/health`, échec du job si la vérification échoue après un délai de 10s) |

### 1.3 Ce qui ne se déclenche jamais automatiquement

- `build`/`deploy` ne tournent **jamais** sur une pull request — seul `test` s'exécute, ce qui empêche de publier une image ou de déployer depuis une branche non fusionnée.
- `deploy` ne tourne que sur `main`, pas sur `develop` — un `push` sur `develop` valide (`test`) et construit l'image (`build`), mais ne déploie pas.
- `deploy` est **ignoré (skip), pas en échec**, tant que la variable `DEPLOY_HOST` n'est pas configurée (`Settings → Secrets and variables → Actions → Variables`) — aucun serveur de production n'est provisionné à ce stade du projet ; le job reste prêt à s'activer dès que cette variable (et les secrets `DEPLOY_USER`/`DEPLOY_SSH_KEY`) seront renseignés, sans qu'il faille modifier le workflow.

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

## 3. Configuration initiale de la CI (installation, pour un fork ou un nouveau dépôt)

Contrairement à l'inventaire des jobs (§1-2), cette section n'existait pas
avant cette vérification. Elle liste ce qu'il faut réellement configurer
dans les paramètres GitHub du dépôt pour que les deux chaînes fonctionnent
de bout en bout — pas seulement ce qui est lu dans les fichiers YAML.

| Élément | Type | Où le créer | Obligatoire ? |
|---|---|---|---|
| `GITHUB_TOKEN` | — | Aucune action requise | Généré et injecté automatiquement par GitHub Actions à chaque run — sert à l'authentification GHCR (job `build`) |
| `DEPLOY_HOST` | Variable (pas secret) | `Settings → Secrets and variables → Actions → Variables → New repository variable` | Non — tant qu'absente, le job `deploy` est **ignoré (skip)**, pas en échec (cf. §1.3) |
| `DEPLOY_USER` | Secret | `Settings → Secrets and variables → Actions → Secrets → New repository secret` | Seulement si `DEPLOY_HOST` est renseignée |
| `DEPLOY_SSH_KEY` | Secret | idem — clé privée SSH complète (format PEM) | Seulement si `DEPLOY_HOST` est renseignée |
| `EXPERT_TOKENS`, `OCR_SPACE_API_KEY`, `ANTHROPIC_API_KEY` | — | **Non requis en CI** | `conftest.py` fixe des valeurs factices (`SCALER_PATH=mock`, clés OCR vides) pour que `ci.yml` reste autonome — ces vraies clés ne servent qu'à l'exécution locale/Docker de l'application, pas aux tests |
| Codecov | — | Aucun token requis pour un dépôt **public** | `codecov/codecov-action@v4` fonctionne sans token sur les dépôts publics ; un token (`CODECOV_TOKEN`, secret) ne serait nécessaire que pour un dépôt privé |

**En pratique, sur un dépôt public comme celui-ci, aucune configuration
manuelle n'est strictement nécessaire pour que `test` et `build`
fonctionnent dès le premier push** — seul le job `deploy` requiert une
étape d'installation volontaire (les 3 lignes `DEPLOY_*` ci-dessus), tant
qu'aucun serveur de production n'est provisionné.

## 4. Preuve d'exécution : les étapes préalables suffisent, depuis un environnement vierge

Preuve que le job `test` de `ci.yml` intègre réellement toutes les étapes
nécessaires avant l'exécution des tests (checkout, setup Python, installation
des dépendances) : la séquence exacte a été rejouée dans un conteneur
`python:3.11-slim` **neuf** (aucun cache pip, aucune dépendance
pré-installée) — pas sur la machine de développement, qui masquerait une
dépendance manquante que la vraie CI détecterait.

```bash
docker run --rm -v "<repo>":/repo -w /repo python:3.11-slim bash -c '
  python --version
  pip install -q -r requirements.txt pytest pytest-cov ruff
  ruff check . --select E,F,W --ignore E501
  DATABASE_URL=sqlite:///:memory: SCALER_PATH=mock OCR_SPACE_API_KEY= ANTHROPIC_API_KEY= \
    pytest tests/ --cov=api --cov-report=term-missing --cov-fail-under=75 -q
'
```

Résultat réel :

```
Python 3.11.15
Dépendances installées.
All checks passed!                                          ← lint
212 passed, 14 warnings in 15.95s                            ← tests
Required test coverage of 75% reached. Total coverage: 80.62%
```

Aucune configuration cachée, aucune dépendance manquante : les étapes
préalables suffisent à elles seules à faire réussir la suite de tests
jusqu'au bout, seuil de couverture inclus. Écart mineur sans rapport avec
ce critère : couverture globale 80.62 % ici contre 82 % en local
(`docs/couverture_execution.md`) — `ocr_service.py` a grossi (128 lignes,
fonction `_extract_json` ajoutée) sans nouveau test dédié pour cette
fonction, diluant légèrement son taux ; le seuil de 75 % reste largement
respecté dans les deux cas.

## 5. Comment déclencher chaque chaîne manuellement (reproduction)

```bash
# ci.yml : uniquement via push/PR, pas de déclenchement manuel possible
git push origin ma-branche   # déclenche `test` (+ `build` si push direct, pas via PR)

# model_ci.yml : déclenchement manuel possible sans toucher aux fichiers surveillés
# Onglet GitHub "Actions" → "Waterflow — CI Modèle ML" → "Run workflow"
# (équivalent CLI : gh workflow run model_ci.yml)
```

## 6. Limites

- Cet inventaire est construit par lecture statique des fichiers YAML — il ne
  constitue pas une preuve d'exécution réelle sur GitHub Actions (nécessiterait
  un push vers le remote et l'observation d'un run réel, hors périmètre de
  cette vérification documentaire).
- §3 liste ce qu'il **faut** configurer, mais ne vérifie pas ce qui est
  **effectivement** configuré dans les paramètres réels du dépôt GitHub
  (accès direct à `Settings → Secrets and variables` non disponible depuis
  cet environnement de vérification) — à confirmer manuellement sur GitHub.

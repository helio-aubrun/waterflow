# Waterflow — Cohérence des outils de test avec l'environnement technique

> Document de preuve : pour chaque couche de l'environnement technique réel
> du projet, identifie l'outil/bibliothèque de test utilisé et justifie ce
> choix — puis vérifie qu'aucun outil de test ne simule une technologie que
> le code de production n'utilise plus. Un écart réel de ce type a été trouvé
> et corrigé (§3) : des résidus de mock MLflow subsistaient après le retrait
> du registre MLflow Model Registry de `predict_service.py`.

## 1. L'environnement technique réel du projet

D'après `requirements.txt` et le code applicatif :

| Rôle | Bibliothèque de production |
|---|---|
| Framework web | Flask 3.x |
| ORM / base de données | SQLAlchemy 2.x (SQLite en dev, PostgreSQL possible en prod) |
| Modèle ML | XGBoost (chargé directement depuis `model_artifacts/xgboost_model.json`) |
| Prétraitement | scikit-learn (`RobustScaler`, `model_artifacts/robust_scaler.pkl`) |
| OCR | OCR.space (HTTP) + Claude Vision (fallback), PyMuPDF pour PDF→image |
| Documentation API | Flasgger (Swagger UI) |
| Serveur de production | Gunicorn |

## 2. Correspondance outil de test ↔ couche technique

| Couche testée | Outil/bibliothèque de test | Où | Pourquoi c'est cohérent |
|---|---|---|---|
| Routes Flask (HTTP) | `app.test_client()` — client de test **natif Flask** | `tests/test_api.py`, `test_fonctionnels.py`, `test_e2e.py` | Pas de serveur réseau réel ni de framework HTTP tiers (ex. `requests` + serveur live) : le client de test appelle directement le WSGI app, rapide et déterministe |
| Base de données (SQLAlchemy) | `sqlite:///:memory:` — même moteur SQLAlchemy qu'en production, juste pointé sur la mémoire | `conftest.py`, `test_api.py`, `test_e2e.py` | Isolation totale entre tests sans mock de l'ORM : le vrai dialecte SQL est exercé, seul le stockage change |
| Modèle XGBoost + scaler scikit-learn | `xgboost.XGBClassifier`, `joblib.load`, `sklearn.metrics.*` (`accuracy_score`, `f1_score`, `roc_auc_score`, `average_precision_score`...) **réutilisés directement, sans réimplémentation** | `tests/test_model_validation.py` (stratégie B, cf. `docs/test_plan_modele.md`) | Les métriques de test sont calculées avec les **mêmes bibliothèques** que celles utilisées à l'entraînement — aucun risque de divergence entre « ce que le test mesure » et « ce que le modèle fait réellement » |
| Appels réseau tiers (OCR.space, Claude Vision) | `unittest.mock.patch`/`MagicMock` (standard lib) | `tests/test_fonctionnels.py`, `test_non_regression.py`, `test_api.py` (`ocr_service`) | Pas de dépendance de test supplémentaire (ex. `responses`, `vcr.py`) pour isoler un appel HTTP externe : la stdlib suffit et évite une dépendance de plus à maintenir |
| Qualité de code | `ruff` | `.github/workflows/ci.yml` | Un seul linter rapide, cohérent avec un projet 100 % Python (pas d'ESLint/Prettier, pas de stack JS) |
| Couverture de test | `pytest-cov` → `--cov-report=xml` + upload Codecov | `.github/workflows/ci.yml` | Plugin `pytest` natif, pas d'outil de couverture externe séparé |
| CI/CD | GitHub Actions, avec un **workflow dédié** (`model_ci.yml`) déclenché uniquement sur changement des artefacts modèle/notebook, distinct du workflow applicatif (`ci.yml`) | `.github/workflows/` | Sépare le cycle de vie du code (à chaque push) de celui du modèle ML (seulement quand les artefacts changent) — évite de re-valider inutilement le modèle à chaque commit de route Flask |

**Choix délibérément écarté** : un framework de test généraliste externe
(Robot Framework, Cucumber/Gherkin) ou un mock-serveur HTTP dédié — `pytest` +
`unittest.mock` + le client de test Flask + les bibliothèques ML natives
couvrent l'intégralité des besoins sans ajouter de dépendance dont
l'environnement technique du projet n'a pas besoin par ailleurs.

## 3. Écart réel trouvé et corrigé : résidus MLflow

`predict_service.py` a été réécrit pour charger XGBoost et le scaler
**directement** depuis `model_artifacts/`, sans passer par le registre MLflow
Model Registry (`mlflow.xgboost.load_model`) — ce dernier dépendait d'un état
local (`mlflow_water.db`) fragile (cf. incident réel corrigé en session
précédente). Après cette réécriture, le code de production n'importe plus
`mlflow` du tout :

```bash
$ grep -rn "import mlflow" api/ scripts/
# (aucun résultat)
```

Mais l'outillage de test simulait encore l'ancien environnement :

| Fichier | Résidu trouvé | Problème |
|---|---|---|
| `tests/test_api.py` | `patch("mlflow.xgboost.load_model", ...)`, `patch("mlflow.set_tracking_uri")` autour de l'import de `create_app` | Patchait une fonction que le code sous test n'appelle plus — le vrai mock du modèle se faisait déjà juste après via `_ps._model = _mock_model` (ligne suivante), rendant le patch MLflow inutile et trompeur |
| `tests/test_api.py`, `tests/test_e2e.py`, `conftest.py` | `os.environ.setdefault("MLFLOW_URI", "mock")` | Variable jamais lue par `predict_service.py` (qui lit `MODEL_PATH`/`SCALER_PATH`) |
| `.github/workflows/ci.yml` (job `test`) | `MLFLOW_URI: mock` dans les variables d'environnement | Même variable fantôme injectée en CI |

**Corrigé** : les 4 fichiers ci-dessus ont été nettoyés (patches et variable
`MLFLOW_URI` supprimés) ; le mock du modèle reste assuré par l'assignation
directe `_ps._model`/`_ps._scaler`, qui correspond exactement à la façon dont
`predict_service.py` charge réellement ses artefacts. `mlflow` reste dans
`requirements.txt` — usage légitime résiduel : le notebook d'entraînement
(`notebooks/water_mlflow_server.ipynb`) l'utilise pour le tracking
d'expériences, un usage **hors ligne de production**, distinct du chemin de
service.

**Preuve que la correction ne casse rien** :

```bash
$ python -m pytest tests/ -q
206 passed, 3 warnings in 7.34s
```

## 4. Limites

- Cette vérification porte sur la cohérence outil↔techno testée ; elle ne
  couvre pas l'exhaustivité de la couverture fonctionnelle (voir
  `docs/test_coverage.md` pour la matrice endpoint × test).
- Les 3 avertissements restants à l'exécution (`InconsistentVersionWarning`
  scikit-learn sur le scaler pickled, `PytestRemovedIn10Warning` sur une
  fixture de classe) sont des avertissements de dépréciation sans impact sur
  le résultat des tests — non corrigés ici car hors du périmètre de cette
  vérification (cohérence des outils, pas leur mise à jour de version).

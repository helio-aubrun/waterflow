# Waterflow — Plan de test du modèle ML

> Document de preuve : liste l'ensemble des cas de test touchant au modèle
> (92 tests, répartis sur 3 fichiers, vérifiés par collecte directe via
> `pytest --collect-only`), avec pour chaque groupe la **partie du
> modèle/pipeline visée**, le **périmètre** et la **stratégie de test**.
> Construit après avoir trouvé une ambiguïté réelle entre deux fichiers au
> vocabulaire proche mais aux garanties différentes (§4) — corrigée en
> distinguant explicitement ici ce qui teste le **vrai** modèle de ce qui
> teste une **simulation** de son comportement.

## 1. Vue d'ensemble — les 4 stratégies de test utilisées

| Stratégie | Ce qu'elle garantit | Ce qu'elle NE garantit PAS |
|---|---|---|
| **A. Unitaire / mock** | La logique autour du modèle (validation, formatage, scaler mocké) fonctionne isolément | Que le vrai modèle produit ces résultats |
| **B. Intégration / artefacts réels** | Le vrai modèle (`model_artifacts/xgboost_model.json`) et le vrai scaler chargés et exécutés produisent des résultats corrects | Le comportement de l'API HTTP autour |
| **C. Contrat API (simulé)** | La forme de la réponse JSON est stable | **Pas** que le modèle réel a produit cette réponse — la prédiction est forcée (`forced_pred`), pas calculée |
| **D. Qualité des données** | Le dataset source est structurellement sain | Rien sur le modèle lui-même |

## 2. `tests/test_unitaires.py` (32 tests) — Stratégie A + D

| Classe (n tests) | Partie visée | Périmètre | Stratégie |
|---|---|---|---|
| `TestValidationEntree` (11, dont 4 paramétrés) | Validation des mesures avant prédiction (features manquantes, non numériques, hors bornes) | Logique de garde côté API, reproduite en isolation — **pas** d'appel au modèle | A — assertions Python pures, aucun mock nécessaire (pas de dépendance externe à isoler) |
| `TestTransformation` (5) | Le `RobustScaler` | Comportement attendu du scaler (shape, appel unique, valeurs extrêmes) | A — **scaler mocké** (`MagicMock`), ne charge pas le vrai `robust_scaler.pkl` |
| `TestPrediction` (10, dont 2 paramétrés) | Formatage de la réponse (`potable`/`label`/`probability`) | Logique pure de mise en forme, réplique manuellement le code de la route | A — fonction `_build_response()` locale au test, **aucun modèle ni scaler impliqué** |
| `TestDataset` (6) | Le dataset source `data/water_potability.csv` | Qualité structurelle (colonnes, doublons, plage pH, valeurs manquantes) | D — lecture directe du CSV réel via pandas |

## 3. `tests/test_model_validation.py` (29 tests) — Stratégie B

> Docstring du fichier : *"Ces tests chargent les vrais artefacts... Ils ne
> mockent rien : ils vérifient que le modèle en production est correct."*
> — la stratégie la plus proche d'une vraie validation du modèle livré.

| Classe (n tests) | Partie visée | Périmètre | Stratégie |
|---|---|---|---|
| `TestArtefacts` (10) | Fichiers `model_artifacts/` (modèle, scaler, metadata, jeux de validation) | Existence, chargeabilité, cohérence des métadonnées (features, shapes) | B — ouverture réelle des fichiers, aucun mock |
| `TestPerformance` (8) | Le modèle XGBoost **réel**, recalcul de ses métriques | Accuracy/F1/ROC-AUC/PR-AUC/CV mean+std/équilibre précision-rappel vs seuils fixes (`THRESHOLDS`) | B — modèle et scaler réels, prédictions recalculées en live sur `X_val_sc.npy`/`y_val.npy` |
| `TestInference` (8) | Comportement du modèle réel sur des entrées contrôlées | Sortie binaire, probabilité dans [0,1], somme des classes = 1, déterminisme, 9 features attendues, inférence batch | B — modèle et scaler réels, échantillons construits à la main (`SAMPLE_POTABLE`, `SAMPLE_DOUTEUX`) |
| `TestStabilite` (3) | Cohérence entre prédictions **live** et prédictions **sauvegardées** à l'entraînement (`y_pred.npy`/`y_pred_prob.npy`) | Détection de toute dérive silencieuse du modèle réel entre deux exécutions | B — comparaison de sorties réelles, tolérance `1e-4` |

## 4. `tests/test_non_regression.py` (31 tests — la totalité du fichier, 5 classes) — Stratégies A/C/D

⚠️ **Point de vigilance** (déjà signalé, documenté ici formellement) : ce
fichier mélange des tests de **contrat** (forme des réponses, stratégie A/C)
et des tests de **qualité de données** (stratégie D) — mais **aucun** de ses
tests ne charge le vrai modèle XGBoost. `TestReproductibilitePredictions`
("golden tests") en particulier **simule** la prédiction via un paramètre
`forced_pred` plutôt que de l'obtenir du modèle réel — à ne pas confondre
avec les garanties, plus fortes, de `test_model_validation.py::TestStabilite`
(§3), qui lui exécute réellement le modèle.

| Classe (n tests) | Partie visée | Périmètre | Stratégie |
|---|---|---|---|
| `TestContratAPI` (11) | Forme de la réponse `/predict` (mockée) et de `/health` | Champs présents, types, code 200/erreur, features acceptées | A — modèle et scaler **mockés** (`MagicMock`, proba fixe) |
| `TestStabilitePreprocessing` (6) | Ordre et nombre de features, shape/dtype de l'array d'entrée | Contrat de préprocessing, pas d'exécution du modèle | A — assertions Python pures |
| `TestReproductibilitePredictions` (5, dont 4 paramétrés) | Formatage `potable`/`label` à partir d'une prédiction **simulée** | ⚠️ Ne teste **pas** le modèle réel malgré le nom "golden tests" — teste la fonction de mise en forme | **C — prédiction forcée (`forced_pred`), pas calculée** |
| `TestMetriquesPerformance` (6) | Distribution des classes et taille du dataset **nettoyé** (`water_potability_clean.csv`), cohérence des seuils baseline documentés (dont comparaison à un classifieur aléatoire) | Qualité/stabilité du jeu de données, pas le modèle en lui-même | D — lecture directe du CSV nettoyé + assertions sur les constantes `BASELINE_METRICS` |
| `TestConfigurationModele` (3) | Chemins de configuration (`MODEL_PATH`, `SCALER_PATH`) et nombre de features déclarées dans l'API | Détection d'une dérive silencieuse de configuration (renommage de fichier, etc.) | A — inspection du **code source** (`inspect.getsource`), pas d'exécution |

Ce fichier ne contient que ces 5 classes (vérifié par `grep "^class Test"
tests/test_non_regression.py`) — il n'y a pas de tests "hors périmètre
modèle" à part dans ce fichier ; les tests d'intégration API pure sont dans
`tests/test_api.py`/`tests/test_fonctionnels.py` (cf. `docs/test_coverage.md`).

## 5. Inventaire complet (vérifié par `pytest --collect-only`, 24/07/2026)

```
tests/test_unitaires.py ............................. 32 tests
tests/test_model_validation.py ....................... 29 tests
tests/test_non_regression.py ......................... 31 tests
──────────────────────────────────────────────────────────────
Total                                                   92 tests
```

Détail par classe (compté en distinguant les cas paramétrés, à partir de
l'arbre produit par `--collect-only`, `<Function ...>` par cas) :

| Fichier | Classe | n tests |
|---|---|---|
| test_unitaires.py | TestValidationEntree | 11 |
| test_unitaires.py | TestTransformation | 5 |
| test_unitaires.py | TestPrediction | 10 |
| test_unitaires.py | TestDataset | 6 |
| test_model_validation.py | TestArtefacts | 10 |
| test_model_validation.py | TestPerformance | 8 |
| test_model_validation.py | TestInference | 8 |
| test_model_validation.py | TestStabilite | 3 |
| test_non_regression.py | TestContratAPI | 11 |
| test_non_regression.py | TestStabilitePreprocessing | 6 |
| test_non_regression.py | TestReproductibilitePredictions | 5 |
| test_non_regression.py | TestMetriquesPerformance | 6 |
| test_non_regression.py | TestConfigurationModele | 3 |
| **Total** | | **92** |

Commande de reproduction (compte le total) :
```bash
pytest tests/test_unitaires.py tests/test_model_validation.py tests/test_non_regression.py --collect-only -q
```

Commande de reproduction (détail par classe, format arbre) :
```bash
pytest tests/test_unitaires.py tests/test_model_validation.py tests/test_non_regression.py --collect-only -q
# lire l'arborescence <Module>/<Class>/<Function> ; chaque <Function> est un
# cas de test (un test paramétré produit une ligne par jeu de paramètres)
```

## 6. Ce que cette organisation garantit — et ce qu'il faudrait ajouter

**Garanti aujourd'hui** : le modèle réel est testé (intégrité, performance
vs seuils, comportement d'inférence, stabilité) indépendamment de l'API
(`test_model_validation.py`), et la logique applicative autour est testée
séparément avec des doubles (`test_unitaires.py`, une partie de
`test_non_regression.py`) — une séparation de préoccupations saine.

**Manquant pour une couverture complète** :
- Aucun test ne vérifie le modèle **à travers** l'API avec les vrais
  artefacts en même temps (l'intégration API teste avec un modèle mocké,
  cf. `tests/test_api.py`, `docs/test_coverage.md` ; la validation modèle
  teste sans passer par l'API) — un test end-to-end avec le **vrai** modèle
  servi par une **vraie** requête HTTP comblerait cet interstice.
- Pas de test de **temps de réponse** du modèle (latence d'inférence),
  seulement des métriques de qualité prédictive.

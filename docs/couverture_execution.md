# Waterflow — Couverture établie et exécution sans problème technique

> Document de preuve : établit la couverture de test **réellement mesurée**
> (par opposition à une estimation manuelle) et démontre que la suite
> s'exécute sans problème technique dans un environnement de test isolé —
> pas seulement sur la machine de développement. Complète
> `docs/test_coverage.md` (couverture qualitative par endpoint) et
> `docs/outils_test.md` (cohérence des outils).

## 1. Couverture souhaitée établie

### 1.1 Ce qui existait avant cette vérification

`RAPPORT_CONFORMITE.md` (daté du 21/06/2026) contenait une **estimation
manuelle** : *« Estimation de couverture globale : ~78 % »*. Ce chiffre n'était
pas produit par un outil de mesure et le rapport lui-même est désormais
obsolète (voir §3) — il ne peut pas servir de seuil de référence fiable.

Aucun seuil numérique de couverture n'était par ailleurs **codifié** ni
**appliqué automatiquement** : `ci.yml` calculait la couverture et l'uploadait
vers Codecov, mais rien n'empêchait une régression de couverture de passer en
CI sans être détectée.

### 1.2 Couverture réellement mesurée (`pytest-cov`)

```bash
pytest tests/ --cov=api --cov-report=term-missing --cov-fail-under=75 -q
```

```
Name                                 Stmts   Miss  Cover   Missing
------------------------------------------------------------------
api/app.py                              16      0   100%
api/middleware/auth.py                 126     21    83%   71-75, 80, 84-88, 93-94, 97-102, 116-120, 126, 148, 179, 184, 209-211, 260-262
api/models/db.py                       121      4    97%   132-135
api/routes/routes.py                   394     38    90%   78, 92-93, 406-410, 424, 469, 510-514, 547-551, 681, 688, 695, 698, 720, 722, 764-768, 771, 775-779, 950, 952, 954
api/services/monitoring_service.py     110     11    90%   99-103, 110, 120, 180, 203, 212, 223
api/services/ocr_service.py            109     87    20%   73-95, 102-136, 143-161, 168-184, 199-220, 233-271
api/services/predict_service.py         34      6    82%   46-51
------------------------------------------------------------------
TOTAL                                  910    167    82%
Required test coverage of 75% reached. Total coverage: 81.65%
```

**82 % de couverture globale mesurée** (au-dessus de l'ancienne estimation
de 78 %).

### 1.3 Le module bas (`ocr_service.py`, 20 %) — écart expliqué, pas un trou

Les lignes non couvertes sont exactement les corps des appels réseau réels :
`_ocr_space()` (appel HTTP à OCR.space) et `_claude_vision_extract()` (appel
à l'API Claude Vision). Les tests mockent délibérément à la frontière du
service (`extract_from_document()`, cf. `tests/test_fonctionnels.py`,
`docs/owasp.md`) plutôt que le détail de la requête HTTP — cohérent avec le
choix documenté dans `docs/outils_test.md` de ne pas ajouter de dépendance de
mock HTTP (type `responses`/`vcr.py`) pour isoler un appel tiers.

### 1.4 Seuil désormais établi et appliqué

`--cov-fail-under=75` ajouté à `ci.yml` (job `test`) : un seuil **inférieur**
à la couverture actuelle (82 %) pour laisser une marge de dégradation
raisonnable tout en bloquant toute régression significative — la CI échoue
désormais explicitement si la couverture chute sous ce seuil, au lieu de se
contenter de la mesurer sans conséquence.

## 2. Exécution sans problème technique en environnement de test

Preuve la plus rigoureuse : exécuter la suite dans un environnement
**complètement isolé** de la machine de développement (autre OS, autre
version de Python, aucun cache résiduel), pas seulement re-vérifier sur la
machine où le code a été écrit.

### 2.1 Machine de développement (Windows, Anaconda, Python 3.11.7)

```
206 passed, 3 warnings in 17.23s
TOTAL   910   167   82%
```

### 2.2 Conteneur Docker frais (Linux, Python 3.11.15 — la vraie image de production)

```bash
docker build -t waterflow-test-env .
docker run --rm \
  -e DATABASE_URL=sqlite:///:memory: -e SCALER_PATH=mock \
  -e OCR_SPACE_API_KEY= -e ANTHROPIC_API_KEY= \
  --entrypoint pytest waterflow-test-env \
  tests/ --cov=api --cov-report=term-missing -q
```

```
206 passed, 3 warnings in 15.35s
TOTAL   910   167   82%
```

**Résultat identique sur les deux environnements** (206 tests passés, 82 %
de couverture) — la suite ne dépend d'aucun état propre à une machine
particulière (pas de fichier laissé par une exécution précédente, pas de
variable d'environnement ambiante non déclarée). Les 3 avertissements
observés dans les deux cas sont des dépréciations sans impact sur le
résultat :
- `InconsistentVersionWarning` (scikit-learn) — le `RobustScaler` a été
  sérialisé avec une version de scikit-learn différente de celle installée
  (1.8.0/1.9.0 vs 1.4.2 selon l'environnement) ; sans effet sur les
  résultats des tests, à surveiller si scikit-learn est mis à jour.
- `PytestRemovedIn10Warning` — une fixture de classe définie comme méthode
  d'instance (pattern à corriger avant pytest 10, hors périmètre de cette
  vérification).

### 2.3 Ce que cela démontre

- Les tests **s'intègrent** au pipeline standard (`pytest tests/`, un seul
  point d'entrée, pas de configuration manuelle par fichier).
- Ils s'exécutent **sans problème technique** aussi bien sur la machine de
  développement que dans l'image Docker réelle de production — pas
  seulement en théorie via la CI GitHub Actions (non déclenchable depuis cet
  environnement de vérification, mais dont la configuration, désormais
  vérifiée manuellement à l'identique via Docker, utilise le même
  `requirements.txt` et les mêmes commandes `pytest`).

## 3. Mise à jour de `RAPPORT_CONFORMITE.md`

Ce rapport datait du 21/06/2026 et listait 4 points « bloquants » — les 3
premiers sont aujourd'hui résolus (vérifié dans cette session et les
précédentes) :

| Point du rapport (21/06/2026) | État réel actuel |
|---|---|
| `ci.yml` à la racine, jamais déclenché | Résolu — `ci.yml`/`model_ci.yml` dans `.github/workflows/` |
| `docs/` gitignoré, absent du dépôt | Résolu — `docs/` versionné, 9 documents présents et référencés depuis le README |
| `test_fonctionnels.py`/`test_non_regression.py` testent `/predict` supprimée, échouent | Résolu — ces fichiers testent les routes actuelles, 206/206 tests passent |
| Filtres absents de la vue analyste web | Non revérifié dans le cadre de cette vérification — hors périmètre (couverture de test, pas UI) |

Le rapport a été mis à jour (voir fichier) pour remplacer l'estimation
obsolète (~78 %, points bloquants résolus) par l'état vérifié ci-dessus, en
conservant une note explicite indiquant qu'il s'agissait de l'état constaté
le 21/06/2026, corrigé depuis.

## 4. Limites

- Cette vérification ne déclenche pas une exécution réelle du workflow
  GitHub Actions (nécessiterait un push vers le remote) — la preuve
  d'exécution repose sur une reproduction manuelle fidèle (mêmes commandes,
  même `requirements.txt`) dans l'image Docker de production, pas sur un
  run CI capturé.
- Le seuil `--cov-fail-under=75` protège contre une régression de couverture
  globale mais n'empêche pas qu'un module spécifique tombe localement plus
  bas tant que la moyenne globale reste au-dessus — une limite acceptée du
  seuil unique choisi (par opposition à un seuil par module, plus rigide).

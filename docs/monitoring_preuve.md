# Waterflow — Preuve de fonctionnement de la chaîne de monitorage

> Document de preuve : met en correspondance chaque métrique **visée** par la
> spécification (US-09, `docs/user_stories.md`) avec la métrique
> **effectivement calculée** (référence code) et **effectivement restituée**
> (référence UI + API), à l'appui d'exécutions réelles capturées — pas
> d'affirmation seule. Complète `docs/test_coverage.md` (couverture des
> tests) et `docs/owasp.md`/`docs/accessibilite.md` (mêmes principes de
> preuve appliqués ici au monitoring du modèle).

## 1. La spécification visée (US-09)

`docs/user_stories.md` :

> **En tant que** responsable d'exploitation, **je veux** être alerté si les
> données reçues en production s'écartent des données d'entraînement,
> **afin d'**anticiper un ré-entraînement avant que le modèle ne se dégrade
> silencieusement.
>
> - **Critères d'acceptation** :
>   - Un score de dérive (PSI) est calculé par variable, avec 3 niveaux
>     (`ok`/`warn`/`critical`), et `insufficient_data` en dessous de 50
>     échantillons pour éviter les faux positifs.
>   - Une alerte est levée si la confiance moyenne des prédictions descend
>     sous 65 % ou si le taux de potabilité dévie de plus de 15 points par
>     rapport à la baseline d'entraînement.

## 2. Métrique visée × calculée × restituée

| Métrique visée (US-09) | Calculée où (code) | Restituée où | Preuve |
|---|---|---|---|
| PSI par variable (9 features) | `monitoring_service.py::compute_drift()` → `_psi()` | API : champ `drift.<feature>.psi` — UI : barre colorée par feature (`psiBar()`, `templates/index.html`) | §3 |
| Niveau `ok`/`warn`/`critical` | `_psi_level()`, seuils `PSI_OK=0.10`/`PSI_WARN=0.20` | API : `drift.<feature>.level` — UI : couleur de la barre + légende | §3 |
| `insufficient_data` sous 50 échantillons | `_psi_level()` : `if n_samples < MIN_SAMPLES_PSI` | API : `level="insufficient_data"` — UI : mention grisée "données insuffisantes" | §3, §4 |
| Alerte confiance < 65 % | `compute_confidence_metrics()` + `compute_alerts()` (type `low_confidence`) | API : `alerts[].type="low_confidence"` — UI : bloc "Confiance moyenne" avec seuil affiché | §3 |
| Alerte dérive potabilité > 15 pts | `compute_alerts()` (type `prediction_drift`), `POTABILITY_DRIFT_WARN=0.15` | API : `alerts[].type="prediction_drift"` — UI : bloc "Taux potabilité prod vs baseline" | §3 |
| Statut global agrégé | `full_report()` : `"critical" if ... else "warn" if ... else "ok"` | API : `global_status` — UI : badge ✅/⚠️/🔴 en tête de dashboard | §3 |

## 3. Preuve d'exécution réelle (capturée le 24/07/2026, via le conteneur Docker de production)

```bash
$ docker compose ps
NAME                     STATUS                    PORTS
waterflow-waterflow2-1   Up 15 minutes (healthy)   0.0.0.0:8080->8080/tcp

$ curl -H "Authorization: Bearer <token-exploit>" \
       "http://localhost:8080/exploitation/monitoring?window_days=30"
```

Réponse réelle obtenue :

```json
{
  "global_status": "ok",
  "n_alerts": 1,
  "n_insufficient": 9,
  "window_days": 30,
  "confidence": {
    "avg_confidence": 0.668,
    "confidence_level": "ok",
    "n_predictions": 5,
    "pct_uncertain": 0.0,
    "potability_rate": 0.8
  },
  "alerts": [
    {
      "type": "prediction_drift",
      "severity": "warning",
      "message": "Dérive du taux de potabilité (80.0% vs baseline 39.0%)",
      "detail": "Écart de 41.0% — seuil d'alerte : 15%"
    }
  ]
}
```

**Ce que cette exécution démontre** : la chaîne calcule et restitue bien les
métriques visées, avec un comportement statistiquement cohérent — sur les 5
vrais prélèvements présents dans ce conteneur, les 9 features sont
correctement classées `insufficient_data` (garde-fou `MIN_SAMPLES_PSI=50`
appliqué, pas de faux `ok`/`critical` sur un échantillon trop petit), tandis
que l'alerte de dérive du taux de potabilité (indépendante du PSI, basée sur
`n_predictions=5` réelles) se déclenche correctement dès lors que l'écart
dépasse le seuil (41 % > 15 %).

## 4. Preuve avec un volume suffisant pour sortir de `insufficient_data`

Capturée en environnement de test dédié (`scripts/init_db.py`, 65-70
prélèvements synthétiques, cf. `docs/test_coverage.md` §"reproduire cette
vérification" pour le détail de la démarche) :

```
ph                 n=65  psi=0.018  level=ok
Hardness            n=65  psi=0.004  level=ok
Chloramines         n=65  psi=0.008  level=ok  (ou =critical, dérive volontaire testée puis retirée — cf. session)
Sulfate              n=65  psi=0.060  level=ok
```

C'est sur ce jeu de test que deux bugs réels de la formule du PSI ont été
trouvés puis corrigés (confusion proportion/comptage dans le lissage de
Laplace ; absence de lissage symétrique côté baseline pour un bin
réellement vide à l'entraînement) — preuve que le calcul est réellement
exercé et vérifié, pas une valeur de façade.

## 5. Restitution dans l'interface (capture d'écran, session de vérification)

Testé avec Playwright (navigateur réel, pas une simulation) :

- Connexion avec un token `exploit` → l'onglet **"🩺 Monitoring"** apparaît
  dans la barre de navigation.
- Connexion avec un token `analyste` → l'onglet est **absent** (masqué côté
  UI en plus du `403` déjà renvoyé par l'API — cf. correctif de
  `showTab()`).
- Clic sur l'onglet (rôle `exploit`) → affiche : statut global (badge
  coloré), nombre d'alertes, une carte "Data Drift par feature (PSI)" avec
  une barre par feature (verte/jaune/rouge/grise), une carte "Dégradation du
  modèle" (confiance moyenne, % incertain, taux de potabilité prod vs
  baseline).

## 6. Couverture de test automatisée

`tests/test_api.py::TestExploitation` — 5 tests dédiés :

| Test | Vérifie |
|---|---|
| `test_monitoring_exploit` | 200 + présence de `global_status`/`drift`/`confidence`/`alerts`/`baseline`/`thresholds` |
| `test_monitoring_analyste_interdit` | 403 pour le rôle `analyste` |
| `test_monitoring_client_interdit` | 401 pour une clé client |
| `test_monitoring_window_days_parametre` | `?window_days=7` bien pris en compte |
| `test_monitoring_window_days_borne_max` | `?window_days=9999` plafonné à 365 |

## 7. Comment reproduire cette vérification

```bash
# 1. Vérifier que le conteneur tourne
docker compose ps

# 2. Appeler l'endpoint avec un vrai token exploit (cf. .env EXPERT_TOKENS)
curl -H "Authorization: Bearer <votre-token-exploit>" \
     "http://localhost:8080/exploitation/monitoring?window_days=30"

# 3. Lancer la suite de tests dédiée
pytest tests/test_api.py::TestExploitation -v

# 4. Vérifier la restitution UI : se connecter sur http://localhost:8080
#    avec un token exploit, cliquer sur l'onglet "Monitoring"
```

## 8. Limites

- Le conteneur Docker actuellement en service n'a que 5 vrais prélèvements
  (seed initial) — insuffisant pour sortir de `insufficient_data` sur les
  scores PSI (comportement attendu, pas un défaut). La démonstration §4
  avec un volume suffisant a été faite en environnement de test dédié, pas
  en re-seedant ce conteneur avec des données synthétiques.
- Cette preuve couvre la chaîne technique (calcul + API + UI + tests) ; elle
  ne constitue pas une validation métier du **choix des seuils**
  (`PSI_OK`, `PSI_WARN`, `CONFIDENCE_WARN`, `POTABILITY_DRIFT_WARN`), qui
  resterait à faire valider par un responsable qualité de l'eau.

# Waterflow — Monitorage applicatif (système, distinct du monitorage modèle)

> Document de preuve : couvre le volet **système** du monitorage
> (`GET /exploitation/metrics` — latence, taux d'erreur par route), en
> complément de `docs/monitoring_preuve.md` qui couvre le volet **modèle**
> (dérive PSI, confiance, taux de potabilité). Un écart réel a été trouvé
> en session de vérification : le monitorage modèle avait des seuils et des
> alertes fonctionnelles (`compute_alerts()`), le monitorage système n'en
> avait **aucun** — corrigé ici (§2), avec preuve d'exécution réelle (§4).

## 1. Pourquoi deux volets de monitorage séparés

| Volet | Question à laquelle il répond | Fichier |
|---|---|---|
| Modèle | *Le modèle prédit-il encore correctement, ou les données de production ont-elles dérivé de l'entraînement ?* | `api/services/monitoring_service.py`, exposé via `GET /exploitation/monitoring` |
| Système (ce document) | *L'API répond-elle correctement et assez vite ?* | `RequestMetric` + `api/routes/routes.py::exploitation_metrics()`, exposé via `GET /exploitation/metrics` |

Ce sont deux risques opérationnels distincts : un modèle qui dérive
silencieusement n'est pas détecté par une latence normale, et une API lente
ou en erreur n'est pas détectée par un PSI stable. D'où deux mécanismes
séparés plutôt qu'un seul indicateur global.

## 2. Métriques, seuils et alertes (système)

| Métrique | Seuil d'alerte | Constante | Où |
|---|---|---|---|
| Taux d'erreur par route (`errors / count`) | > 5 % | `ERROR_RATE_WARN = 0.05` | `api/routes/routes.py` |
| Latence p95 par route | > 2000 ms | `P95_WARN_MS = 2000` | `api/routes/routes.py` |

**Exception documentée** : les routes OCR (`/ingest/ocr`,
`/ingest/ocr-and-predict`) sont **exclues** du seuil de latence
(`OCR_ROUTES`). Elles dépendent d'appels réseau réels à des API tierces
(OCR.space, Claude Vision) — une p95 de plusieurs dizaines de secondes y
est **normale** (mesuré réellement à ~40s sur un cas réel lors du
basculement vers le service de secours, cf. `docs/preuve_ocr_c8.md`) : leur
appliquer le seuil de 2s déclencherait une alerte permanente et sans valeur
diagnostique. Le taux d'erreur, lui, reste surveillé sur ces routes comme
sur les autres.

## 3. Pourquoi cet outillage (choix technique) plutôt que Prometheus/Grafana

Ce choix n'était justifié nulle part avant cette vérification —
`README.md` le mentionnait seulement comme une limite connue, jamais comme
un arbitrage assumé. Pour un projet à cette échelle (solo, MVP) :

- **Aucune infrastructure supplémentaire à opérer** : une table SQL
  (`request_metrics`) et un endpoint API suffisent, alors que
  Prometheus/Grafana demanderaient un service supplémentaire à déployer,
  configurer et maintenir dans `docker-compose.yml`.
- **Cohérent avec la stack existante** : SQLAlchemy et Flask sont déjà les
  outils du projet — pas de nouveau langage de configuration (PromQL) ni de
  nouvelle dépendance à isoler pour un besoin de supervision basique.
- **Suffisant pour le volume réel actuel** (quelques dizaines de
  prélèvements en démonstration, cf. `docs/monitoring_preuve.md` §3) —
  Prometheus/Grafana serait pertinent à un volume de requêtes et un nombre
  d'exploitants plus élevés, identifié comme piste d'évolution
  (`README.md` « Limites connues »), pas comme un besoin actuel.

## 4. Preuve d'exécution réelle des alertes (tests, pas seulement code)

Les seuils ne sont pas seulement déclarés : ils sont vérifiés par deux
tests réels qui insèrent des données contrôlées en base puis interrogent
l'endpoint réel (`tests/test_api.py::TestExploitation`) :

```python
def test_metrics_alerte_taux_erreur(self, http):
    # 10 requêtes, 2 en erreur (400) => 20% > seuil 5%
    ...
    assert len(alertes_erreur) == 1

def test_metrics_pas_alerte_latence_route_ocr(self, http):
    # 5 requêtes OCR à 40000ms (40s) => aucune alerte de latence attendue
    ...
    assert alertes_latence_ocr == []
```

```bash
$ pytest tests/test_api.py::TestExploitation -v
test_metrics_alerte_taux_erreur PASSED
test_metrics_pas_alerte_latence_route_ocr PASSED
13 passed in 1.79s
```

Suite complète après cet ajout : **214/214 tests passent** (212 précédents
+ 2 nouveaux).

## 5. Installation et dépendances

Aucune dépendance supplémentaire : le monitorage système réutilise
`SQLAlchemy` (déjà dans `requirements.txt`) et la table `RequestMetric`
déjà créée par `init_db()`. Rien à installer ou configurer séparément —
contrairement à un outil externe (Prometheus/Grafana), qui aurait nécessité
une procédure d'installation dédiée.

## 6. Comment reproduire cette vérification

```bash
# 1. Lancer les tests dédiés
pytest tests/test_api.py::TestExploitation -v

# 2. Appeler l'endpoint réel avec un token exploit
curl -H "Authorization: Bearer <token-exploit>" \
     "http://localhost:8080/exploitation/metrics"
# -> champs "alerts" et "thresholds" dans la réponse
```

## 7. Limites

- Les seuils (`ERROR_RATE_WARN=5%`, `P95_WARN_MS=2000`) sont des valeurs de
  départ raisonnables mais non calibrées sur un historique de production
  réel (le projet est encore en phase de démonstration) — à ajuster une
  fois un volume de trafic réel observé.
- Contrairement au monitorage modèle (`docs/monitoring_preuve.md`), ces
  alertes système ne sont pas encore relayées par notification (e-mail,
  push) ni affichées dans l'onglet Monitoring de l'UI — seulement
  disponibles via l'appel API direct à ce stade.
- **Précision suite à une confusion trouvée en vérification** : le test
  Playwright réel documenté dans `docs/monitoring_preuve.md` §5 (onglet
  "🩺 Monitoring" visible/masqué selon le rôle, cartes de dérive affichées)
  porte sur `GET /exploitation/monitoring` (volet **modèle**) — ce n'est
  **pas** une preuve d'affichage UI pour `GET /exploitation/metrics` (ce
  document, volet système), qui n'a aucune restitution graphique à ce jour,
  comme indiqué au point précédent.

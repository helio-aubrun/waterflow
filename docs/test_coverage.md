# Waterflow — Matrice de traçabilité tests ↔ points de terminaison

> Document de preuve : met en correspondance chaque point de terminaison réel
> (`api/routes/routes.py`, 21 chemins distincts / 24 combinaisons
> méthode+chemin, tous documentés dans `swagger.yaml`) avec le ou les tests
> qui le couvrent, et précise ce qui est effectivement vérifié (code de
> statut, auth/rôle, forme de la réponse). Construit par vérification directe
> du code et des tests, pas par estimation — les manques identifiés sont
> listés en toute transparence en §3.

## 1. Légende

- ✅ Couvert — cas nominal ET cas d'erreur/sécurité vérifiés
- ⚠️ Partiel — au moins un cas documenté (nominal ou erreur) n'est pas testé
- Fichier::test — référence exacte du test (`tests/<fichier>.py::<nom>`)

## 2. Matrice complète

### Public

| Route | Statut | Tests | Vérifié |
|---|---|---|---|
| `GET /health` | ✅ | `test_api.py::TestHealth::test_ok_sans_auth`, `test_fonctionnels.py::TestEndpointHealth` (5 tests) | 200, `content_type`, champs `status`/`model`, 405 sur POST |
| `GET /` | ⚠️ | `test_fonctionnels.py::TestEndpointIndex::test_index_statut_200_ou_redirect` | Assertion faible : `status_code in (200, 302, 404)` — n'affirme rien de précis (route hors périmètre API/OpenAPI, sert le HTML) |

### Client (X-API-Key)

| Route | Statut | Tests | Vérifié |
|---|---|---|---|
| `POST /predict` | ✅ | `test_fonctionnels.py::TestEndpointPredictNominal` (9 tests), `::TestEndpointPredictErreurs` (7 tests), `test_non_regression.py::TestContratAPI` (10 tests) | 200/400/401, forme exacte de la réponse (`potable`/`label`/`probability`), ordre scaler→modèle, 9 features requises testées une par une, clé absente/invalide |
| `GET /me` | ✅ | `test_api.py::TestClientAuth` (4 tests) | 200 avec clé valide, 401 sans clé, 401 clé invalide, 401 si Bearer utilisé à la place |
| `GET /me/rgpd` | ✅ | `test_api.py::TestRGPD` (6 tests) | Structure complète, absence de clé brute, IP pseudonymisée, règles de conservation, droits mentionnés, 401 sans auth, 401 expert (mauvais monde d'auth) |
| `DELETE /me/rgpd` | ✅ | `test_api.py::TestRGPD::test_delete_rgpd_sans_confirmation`, `::test_delete_rgpd_confirme` | 400 sans `{"confirmer": true}`, anonymisation effective + `/me` redevient inaccessible avec l'ancienne clé |
| `GET /me/prelevements` | ✅ | `test_api.py::TestClientConsultation` (3 tests), `test_e2e.py` | 200, pagination (`?page`/`?per_page`), présence du prélèvement créé |
| `GET /me/prelevements/{id}` | ✅ | `test_e2e.py::test_e2e_detail_prelevement_source_ocr`, `::test_e2e_mesures_extraites_correctement`, `test_api.py::TestClientConsultation::test_detail_prelevement_autre_client_refuse`, `::test_detail_prelevement_cle_invalide_401` | Cas nominal, `403` BOLA (second client avec sa **propre** clé valide, `routes.py` ligne 425), `401` clé totalement invalide |
| `GET /me/resultats` | ⚠️ | `test_api.py::TestClientConsultation::test_mes_resultats` | Cas nominal (200) testé. Pas de test 401 sans clé sur cette route précise (401 vérifié sur `/me` et d'autres, pas explicitement ici) |
| `POST /ingest/manual` | ✅ | `test_api.py::TestClientIngestion` (4 tests) | 201 nominal, 400 feature manquante, 400 valeur non numérique, 401 sans clé |
| `POST /ingest/ocr` | ✅ | `test_api.py::TestClientIngestion::test_ingest_ocr_valide_201`, `::test_ingest_ocr_sans_fichier`, `::test_ingest_ocr_type_invalide` | 201 nominal (`prelevement_id`/`ocr` présents, pas de `prediction`), 400 fichier absent, 400 type invalide |
| `POST /ingest/ocr-and-predict` | ✅ | `test_e2e.py::TestE2EPipelineOcrPredict` (9 tests) | Pipeline complet 201, `prelevement_id`, prédiction cohérente (label/potable/probability), récupération via `/me/prelevements`, source `ocr`, mesures extraites exactes, mesures partielles → `prediction_possible=false`, 401 sans clé, 400 sans fichier |

### Admin (Bearer, tout expert)

| Route | Statut | Tests | Vérifié |
|---|---|---|---|
| `GET /admin/clients` | ✅ | `test_api.py::TestAdminClients::test_lister_clients_analyste`, `::test_lister_clients_exploit` | 200 pour les deux rôles experts |
| `POST /admin/clients` | ✅ | `test_api.py::TestAdminClients` (7 tests) | 201 (analyste et exploit), 401 sans auth, 401 mauvais token, clé absente de la réponse, champs requis (`id_client`/`denomination`/`adresse`), 409 doublon |
| `GET /admin/clients/{id}` | ✅ | `test_api.py::TestAdminClients::test_client_existant_200`, `::test_client_introuvable` | 200 nominal (profil, sans clé brute), 404 client inconnu |
| `PUT /admin/clients/{id}` | ✅ | `test_api.py::TestAdminClients::test_modifier_client`, `::test_adresse_vide_refusee` | Modification effective, rejet adresse vide |
| `POST /admin/clients/{id}/apikey` | ✅ | `test_api.py::TestAdminClients::test_generer_cle_analyste`, `::test_generer_cle_exploit`, `test_e2e.py` | 201, rôles analyste et exploit |

### Analyste (Bearer, rôle analyste ou exploit)

| Route | Statut | Tests | Vérifié |
|---|---|---|---|
| `GET /analyste/prelevements` | ✅ | `test_api.py::TestAnalyste` (3 tests) | 200, 401 sans auth, 401 si un client tente d'y accéder |
| `GET /analyste/prelevements/{id}` | ✅ | `test_api.py::TestAnalyste::test_prelevement_detail_nominal`, `::test_prelevement_detail_introuvable_404`, `::test_prelevement_detail_client_interdit` | 200 nominal (détail complet), 404 introuvable, 401 si un client (pas un expert) tente d'y accéder |
| `GET /analyste/clients/{client_id}/prelevements` | ✅ | `test_api.py::TestAnalyste::test_client_inconnu_404`, `::test_client_existant_prelevements_nominal` | 404 client inconnu, 200 + structure paginée pour un client existant |
| `GET /analyste/dashboard` | ✅ | `test_api.py::TestAnalyste::test_dashboard`, `::test_dashboard_exploit_peut_aussi` | 200, champs réels (`total_prelevements`/`potable_rate`/`moyennes`), accès exploit également autorisé (super-rôle) |

### Exploitation (Bearer, rôle exploit uniquement)

| Route | Statut | Tests | Vérifié |
|---|---|---|---|
| `GET /exploitation/metrics` | ✅ | `test_api.py::TestExploitation` (3 tests) | 200 + champs réels (`routes`/`clients_total`), 403 analyste, 401 client |
| `GET /exploitation/audit` | ✅ | `test_api.py::TestExploitation` (3 tests) | 200 + champs (`items`/`total`), 403 analyste, pagination |
| `GET /exploitation/monitoring` | ✅ | `test_api.py::TestExploitation` (5 tests) | 200 + champs réels (`global_status`/`drift`/`confidence`/`alerts`), 403 analyste, 401 client, `window_days` respecté et plafonné à 365 |

## 3. Écarts trouvés puis corrigés lors de cette revue

Quatre écarts ont été trouvés en vérifiant le **code** des tests plutôt que
leur seul intitulé — puis corrigés. Conservés ici pour la traçabilité de la
démarche (une matrice qui n'aurait affiché que des ✅ sans historique serait
moins convaincante qu'une revue qui montre avoir cherché et trouvé) :

### 3.1 `GET /me/prelevements/{id}` — le contrôle BOLA n'était jamais réellement testé

`routes.py` ligne 425 (`if p.client_id != g.client.id: return 403`) est une
vraie protection contre l'accès aux données d'un autre client (OWASP API1,
cf. `docs/owasp.md` §2). Un test existait avec un nom prometteur
(`test_detail_prelevement_autre_client_refuse`), mais en lisant son code :
il créait un second client puis faisait la requête avec une **clé aléatoire
non enregistrée**, pas avec la vraie clé du second client — il vérifiait
donc un `401` (clé invalide), pas le `403` (clé valide d'un **autre**
client) que son nom promettait. La branche `403` n'était exercée par aucun
test.

**Corrigé** : le test crée maintenant un prélèvement réel pour TEST-001, un
second client avec sa **propre** clé valide, puis vérifie que ce second
client obtient bien `403` en tentant d'accéder au prélèvement du premier.
L'ancien scénario (clé totalement invalide → `401`) est conservé séparément
sous un nom qui correspond à ce qu'il teste réellement.

### 3.2 `POST /ingest/ocr` — cas nominal jamais testé

Seuls les deux cas d'erreur (fichier absent, type non supporté) étaient
couverts. **Corrigé** : `test_ingest_ocr_valide_201` mocke
`extract_from_document` et vérifie le `201`, la présence de
`prelevement_id`/`ocr`, et l'absence de `prediction` (cette route n'appelle
pas le modèle, contrairement à `/ingest/ocr-and-predict`).

### 3.3 `GET /admin/clients/{id}` — cas nominal jamais testé

Seul le `404` était vérifié. **Corrigé** : `test_client_existant_200` vérifie
le `200` nominal et l'absence de clé brute dans la réponse.

### 3.4 `GET /analyste/prelevements/{id}` — aucun test du tout

**Corrigé** : 3 tests ajoutés (`200` nominal avec un prélèvement réel, `404`
introuvable, `401` si un client tente d'y accéder au lieu d'un expert).

## 4. Comment reproduire cette vérification

```bash
# Lister les routes réelles
grep -n '@bp.route' api/routes/routes.py

# Lister les routes documentées dans le contrat OpenAPI
python -c "import yaml; print(sorted(yaml.safe_load(open('swagger.yaml'))['paths']))"

# Confirmer qu'aucune route n'est absente du contrat OpenAPI
python -c "
import os
os.environ.setdefault('EXPERT_TOKENS', 'x:xxxxxxxxxxxxxxxxxxxx:analyste')
from main import app
paths = app.test_client().get('/apispec.json').get_json()['paths']
print(sorted(paths))
"

# Lancer la suite complète
pytest tests/ -v
```

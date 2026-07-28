# Waterflow — Preuve de concept accessible et fonctionnelle en pré-production

> Document de preuve : appuie `docs/architecture.md` §6 (*« La preuve de
> concept est l'application elle-même, fonctionnelle en environnement de
> pré-production »*) avec une exécution réelle capturée — build, démarrage,
> accessibilité et fonctionnalité vérifiées via la vraie stack Docker
> Compose, pas seulement affirmées.

## 1. Build et démarrage réels

```bash
$ docker compose up -d --build
 Image waterflow-waterflow2 Built
 Container waterflow-waterflow2-1 Started

$ docker compose ps
NAME                     STATUS                    PORTS
waterflow-waterflow2-1   Up 17 seconds (healthy)   0.0.0.0:8080->8080/tcp
```

Le conteneur passe à l'état `healthy` (healthcheck Docker défini dans
`Dockerfile` : `curl -f http://localhost:8080/health`) sans intervention
manuelle.

## 2. Accessibilité réelle

| Vérification | Commande | Résultat réel |
|---|---|---|
| Santé de l'API | `curl http://localhost:8080/health` | `{"model":"xgboost_model.json","status":"ok",...}` |
| Interface web | `curl -o /dev/null -w "%{http_code}" http://localhost:8080/` | `200` |
| Documentation Swagger | `curl -o /dev/null -w "%{http_code}" http://localhost:8080/apidocs` | `200` |

Le champ `"model":"xgboost_model.json"` dans `/health` confirme que le
correctif de chargement direct du modèle (sans registre MLflow, cf.
`docs/outils_test.md`) est bien actif **dans l'image construite**, pas
seulement dans les sources — preuve que le build Docker reflète l'état réel
du code, pas une version figée obsolète.

## 3. Fonctionnalité réelle (pas seulement « ça répond »)

```bash
# Peuplement de la base de démonstration, dans le conteneur
$ docker compose exec waterflow2 python scripts/init_db.py

# Appel authentifié réel (rôle exploit, token issu de EXPERT_TOKENS)
$ curl -H "Authorization: Bearer <token-exploit>" \
       http://localhost:8080/exploitation/metrics
```

```json
{
  "clients_total": 3,
  "clients_actifs": 2,
  "total_prelevements": 70,
  "total_predictions": 70,
  "potable_rate": 0.5429
}
```

Cette réponse démontre, dans la stack conteneurisée réelle :
- la persistance des données (SQLite dans le volume `waterflow_data`) ;
- l'authentification experte fonctionnelle, donc `EXPERT_TOKENS` correctement
  transmis au conteneur (`docker-compose.yml` — point corrigé lors d'une
  vérification précédente : cette variable n'était historiquement pas
  répercutée depuis `.env`) ;
- le pipeline de prédiction complet exécuté 70 fois avec succès
  (`total_predictions: 70`).

### 3.1 Capture complémentaire (session distincte, serveur local non-Docker)

La capture ci-dessus (§3) a été volontairement tronquée aux champs résumé.
Le détail par route (`p50_ms`/`p95_ms`/`error_rate`, cf.
`docs/monitorage_applicatif.md`) a bien été vérifié réellement, mais lors
d'une **session de vérification distincte** (serveur local, pas Docker) —
présenté ici séparément plutôt que fusionné avec la capture Docker
ci-dessus, pour ne pas laisser croire à une seule exécution unique alors
que les deux runs ont des états de base différents (67 vs 70 prédictions) :

```json
{
  "clients_total": 3, "clients_actifs": 2,
  "total_prelevements": 68, "total_predictions": 67, "potable_rate": 0.5075,
  "sample_size": 21,
  "routes": {
    "GET /analyste/dashboard":      { "count": 3,  "error_rate": 0.0, "p50_ms": 170.0,   "p95_ms": 175.2 },
    "GET /exploitation/metrics":    { "count": 1,  "error_rate": 0.0, "p50_ms": 20.7,    "p95_ms": 20.7 },
    "GET /exploitation/monitoring": { "count": 1,  "error_rate": 0.0, "p50_ms": 15.3,    "p95_ms": 15.3 },
    "GET /me/prelevements":         { "count": 14, "error_rate": 0.0, "p50_ms": 98.5,    "p95_ms": 188.9 },
    "POST /ingest/ocr-and-predict": { "count": 2,  "error_rate": 0.0, "p50_ms": 40391.9, "p95_ms": 40391.9 }
  }
}
```

Cette capture confirme que le détail par route existe réellement (pas
seulement dans le schéma), et que la latence p95 anormalement élevée sur
`POST /ingest/ocr-and-predict` (~40s, appel réel à OCR.space + bascule
Claude Vision) est exactement le cas d'usage réel qui justifie l'exclusion
de cette route du seuil d'alerte de latence (`docs/monitorage_applicatif.md` §2).

**Limite de cette preuve** : les deux captures (§3 et §3.1) proviennent de
deux exécutions réelles distinctes, pas d'un seul run reproductible d'un
bout à l'autre — une future vérification pourrait les unifier en relançant
`docker compose up -d --build` puis en interrogeant `/exploitation/metrics`
une seule fois pour obtenir une capture unique et cohérente.

## 4. Comment reproduire cette vérification

```bash
cp .env.example .env
# éditer .env : au moins une clé OCR (OCR_SPACE_API_KEY ou ANTHROPIC_API_KEY)
# et EXPERT_TOKENS (login:token:role,...)

docker compose up -d --build
docker compose ps                                  # doit afficher "healthy"
docker compose exec waterflow2 python scripts/init_db.py
curl http://localhost:8080/health

# puis ouvrir http://localhost:8080 (interface) et
# http://localhost:8080/apidocs (documentation API) dans un navigateur
```

Arrêt : `docker compose down` (ajouter `-v` pour supprimer aussi le volume
de données de démonstration).

## 5. Limites

- Cette preuve couvre l'environnement de **pré-production local**
  (Docker Compose sur la machine de développement), pas un déploiement réel
  sur l'environnement cible de production (SSH + serveur distant, cf.
  `docs/chaine_cicd.md` job `deploy`) — ce dernier n'est pas encore activé
  faute de serveur provisionné (`vars.DEPLOY_HOST` non configuré).
- La vérification fonctionnelle porte sur les routes d'administration et de
  métriques (rôle `exploit`) ; elle ne rejoue pas systématiquement tous les
  parcours utilisateurs (`docs/parcours_utilisateurs.md` pour l'inventaire
  complet des parcours à tester lors d'une recette plus large).

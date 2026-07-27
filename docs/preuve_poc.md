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

# Waterflow — Conformité OWASP API Security Top 10 (2023)

> Document reconstruit à partir de l'implémentation existante (middleware
> d'authentification, modèle de données, routes) pour formaliser a posteriori
> le rattachement des mesures de sécurité déjà en place aux catégories de
> l'OWASP API Security Top 10 (édition 2023). Aucune de ces mesures n'a été
> conçue à l'origine en citant explicitement l'OWASP — ce document établit la
> correspondance et identifie les manques.

## 1. Synthèse

| Catégorie | Statut | Détail |
|---|---|---|
| API1:2023 — Broken Object Level Authorization | ✅ Couvert | §2 |
| API2:2023 — Broken Authentication | ✅ Couvert | §3 |
| API3:2023 — Broken Object Property Level Authorization | ⚠️ Partiel | §4 |
| API4:2023 — Unrestricted Resource Consumption | ⚠️ Partiel | §5 |
| API5:2023 — Broken Function Level Authorization | ✅ Couvert | §6 |
| API6:2023 — Unrestricted Access to Sensitive Business Flows | ❌ Non couvert | §7 |
| API7:2023 — Server Side Request Forgery | N/A | §8 |
| API8:2023 — Security Misconfiguration | ⚠️ Partiel | §9 |
| API9:2023 — Improper Inventory Management | ✅ Couvert | §10 |
| API10:2023 — Unsafe Consumption of APIs | ⚠️ Partiel | §11 |

## 2. API1:2023 — Broken Object Level Authorization (BOLA)

**Risque couvert** : qu'un client authentifié accède aux données d'un autre
client en devinant/forçant un identifiant de ressource.

**Implémentation** (`api/routes/routes.py`) :

```python
@bp.route("/me/prelevements/<string:prev_id>", methods=["GET"])
@require_client_key
def me_prelevement_detail(prev_id: str):
    p = g.db.query(Prelevement).filter(Prelevement.id == prev_id).first()
    if not p:
        return jsonify({"error": "Prélèvement introuvable."}), 404
    if p.client_id != g.client.id:
        return jsonify({"error": "Accès refusé."}), 403
```

La vérification `p.client_id != g.client.id` est explicite, pas seulement
implicite via un filtre de requête — même en connaissant l'identifiant exact
d'un prélèvement d'un autre client, l'accès est refusé (`403`). Le même
principe s'applique à `/me/resultats` (filtre `Prelevement.client_id ==
g.client.id` directement dans la requête SQL, ligne 443).

## 3. API2:2023 — Broken Authentication

**Risque couvert** : compromission ou contournement du mécanisme
d'authentification.

**Implémentation** (`api/middleware/auth.py`) :

- Clés API clients **hashées SHA-256**, jamais stockées en clair
  (`Client.hash_key`, `Client.set_api_key`) — un accès à la base ne permet pas
  de retrouver une clé en clair.
- Comparaison des tokens experts en **temps constant**
  (`hashlib.compare_digest`, `_resolve_expert`) — protège contre les attaques
  par mesure du temps de réponse.
- Messages d'erreur **génériques** en cas d'échec ("Clé API invalide ou
  absente.") — ne confirme jamais si la clé existe mais est invalide, ou si
  le compte est désactivé.
- Vérification du statut **actif** du compte en plus de la validité de la clé
  (`Client.actif == True`) — une clé par ailleurs valide d'un compte
  désactivé est rejetée.
- Toute tentative échouée est journalisée (`_write_audit`, `action:
  "auth_failed"`), avec l'IP pseudonymisée.

**Correction récente** : la route `POST /predict` était jusqu'ici accessible
**sans authentification** ("usage demo/test"). Elle est désormais protégée
par `@require_client_key`, au même titre que `/ingest/manual` et
`/ingest/ocr-and-predict` — le modèle d'IA n'est plus interrogeable sans
identité vérifiée.

## 4. API3:2023 — Broken Object Property Level Authorization

**Risque partiellement couvert** : qu'une réponse expose des champs que
l'appelant ne devrait pas voir, ou qu'une requête accepte des champs qu'il ne
devrait pas pouvoir modifier.

Ce qui est fait :
- La clé API brute n'apparaît **jamais** dans aucune réponse JSON (vérifié
  dans `tests/test_api.py`, assertions `"api_key" not in d"`), seul
  `api_key_hint` (4 premiers caractères) est exposé.
- `GET /me` ne renvoie que les champs pertinents pour le client authentifié
  lui-même, pas les champs internes (`api_key_hash`, `created_by`).

Ce qui manque :
- Aucune validation de schéma stricte des corps de requête entrants (ex:
  `PUT /admin/clients/<id>`) empêchant explicitement l'injection de champs
  non prévus dans le payload JSON — la protection actuelle repose sur le fait
  que le code ne lit que les clés qu'il attend, pas sur un rejet explicite des
  clés en trop (« mass assignment » non testé formellement).

## 5. API4:2023 — Unrestricted Resource Consumption

**Risque partiellement couvert** : épuisement de ressources serveur par des
requêtes volumineuses ou répétées.

Ce qui est fait (`api/routes/routes.py`) :
- Upload de fichiers limité à **20 Mo** (`MAX_UPLOAD_BYTES`) et type MIME
  validé (`ACCEPTED_MIME`) **avant** tout traitement OCR coûteux
  (`_read_upload`).
- Pagination systématique sur toutes les routes de liste (`/me/prelevements`,
  `/analyste/prelevements`, etc.) — pas de renvoi de l'intégralité d'une
  table en une seule réponse.

Ce qui manque (déjà identifié dans le README, "Limites connues") :
- **Aucun rate limiting** — un client avec une clé valide peut appeler
  `/predict` ou `/ingest/*` un nombre illimité de fois par seconde. À traiter
  au niveau du reverse proxy (ex: Nginx `limit_req`, ou une solution comme
  Flask-Limiter) avant une mise en production réelle.

## 6. API5:2023 — Broken Function Level Authorization

**Risque couvert** : qu'un utilisateur avec un rôle limité accède à des
fonctions réservées à un rôle supérieur.

**Implémentation** (`api/middleware/auth.py`, `require_expert(role=...)`) :

```python
if role and expert_role != "exploit" and expert_role != role:
    return jsonify({"error": f"Accès refusé. Rôle requis : '{role}'."}), 403
```

Les routes `/exploitation/metrics` et `/exploitation/audit` exigent le rôle
`exploit` ; `/analyste/*` accepte `analyste` **ou** `exploit` (super-rôle
explicite et documenté, pas une confusion accidentelle de rôles).

## 7. API6:2023 — Unrestricted Access to Sensitive Business Flows

**Non couvert.** Cette catégorie vise les flux métier sensibles consommés de
façon automatisée/abusive (ex: création massive de comptes, appels
répétés à un flux de prédiction pour en épuiser un quota implicite). Aucune
détection de ce type de comportement (fréquence anormale d'un même client,
CAPTCHA, limitation métier au-delà du simple rate limiting technique) n'est
implémentée. Risque jugé faible au stade actuel (accès B2B par clé API
attribuée manuellement à des collectivités, pas d'inscription publique en
self-service), mais à réévaluer si le modèle d'accès change.

## 8. API7:2023 — Server Side Request Forgery (SSRF)

**Non applicable en l'état.** L'API ne prend aucune URL fournie par
l'utilisateur pour effectuer une requête serveur sortante — les seuls appels
sortants (`OCR.space`, `Anthropic`) utilisent des endpoints codés en dur dans
`api/services/ocr_service.py`, jamais une URL issue d'un paramètre de
requête client.

## 9. API8:2023 — Security Misconfiguration

Ce qui est fait :
- Conteneur Docker exécuté par un **utilisateur non-root** (`Dockerfile`,
  `useradd -m -u 1000 waterflow` + `USER waterflow`).
- `FLASK_ENV=production` forcé dans `docker-compose.yml` → `debug=False`
  dans `main.py` → pas de stack trace Werkzeug exposée en cas d'erreur 500.
- IPs pseudonymisées avant tout stockage en base (`_pseudo_ip`).

Ce qui manque (déjà identifié dans le README) :
- **Pas de CORS configuré** — non bloquant tant qu'aucun frontend séparé ne
  consomme l'API depuis un autre domaine, mais à prévoir avant.
- Pas de en-têtes de sécurité HTTP explicites (`Strict-Transport-Security`,
  `X-Content-Type-Options`, etc.) — à ajouter au niveau du reverse proxy en
  production.

## 10. API9:2023 — Improper Inventory Management

**Couvert.** Deux symptômes corrigés :

1. `/predict` n'était pas documentée dans le contrat OpenAPI (`swagger.yaml`)
   alors qu'elle existait et exposait un accès direct au modèle. Corrigée :
   documentée (sécurité `ApiKeyHeader`, schéma de requête/réponse), vérifiée
   présente dans `/apispec.json` généré par Flasgger.
2. Les schémas de réponse documentés pour `/exploitation/metrics` et
   `/analyste/dashboard` ne correspondaient **pas du tout** aux champs
   réellement renvoyés par le code (`metrics_by_route` documenté vs `routes`
   réellement renvoyé ; `taux_potabilite` documenté vs `potable_rate`
   réellement renvoyé, etc.) — un inventaire "à jour dans sa liste de routes"
   mais faux dans son contenu, tout aussi trompeur pour un consommateur de
   l'API. Corrigé : `DashboardResponse` et `MetricsResponse` reflètent
   désormais exactement les clés retournées par
   `analyste_dashboard()`/`exploitation_metrics()`.

3. `/analyste/clients/{client_id}/prelevements` et `/exploitation/monitoring`
   existaient dans le code (et étaient déjà couvertes par des tests) mais
   étaient elles aussi absentes de `swagger.yaml` — même symptôme que
   `/predict`. Corrigées : les 20 chemins distincts de
   `api/routes/routes.py` sont désormais tous les 20 présents dans
   `swagger.yaml` (vérifié par comparaison directe, pas par estimation).

Point de vigilance permanent : rien n'impose automatiquement que
`swagger.yaml` reste synchronisé avec `api/routes/routes.py` (pas de
génération du schéma à partir du code) — seule une revue régulière (comme
celle-ci) le garantit.

## 11. API10:2023 — Unsafe Consumption of APIs

**Partiellement couvert.** L'API consomme deux services tiers (OCR.space,
Claude Vision) documentés dans `docs/rgpd.md` §7. Le traitement de leur
réponse (texte extrait) alimente ensuite le modèle de prédiction sans étape
de validation de contenu explicite décrite dans le code au-delà de la
structure JSON attendue — un contenu malicieux injecté par un service tiers
compromis n'est pas explicitement testé comme scénario.

## 12. Limites identifiées et actions prioritaires

1. **Rate limiting absent** (§5) — action recommandée avant montée en charge.
2. **CORS et en-têtes de sécurité HTTP absents** (§9) — à traiter au niveau
   du reverse proxy de production.
3. **Pas de validation de schéma stricte contre le "mass assignment"** (§4)
   sur les routes d'écriture (`PUT /admin/clients/<id>`).
4. Cette analyse est une reconstruction a posteriori : elle devrait être
   revue à chaque ajout de route, pas seulement documentée une fois — comme
   le montre le cas `/predict` (§10), corrigé mais qui aurait pu passer
   inaperçu indéfiniment sans cette revue.

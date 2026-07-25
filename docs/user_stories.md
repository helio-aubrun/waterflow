# Waterflow — User Stories

> Document reconstruit à partir de l'application existante (routes, rôles et comportements
> implémentés) pour formaliser a posteriori le besoin métier. Formalisme : *En tant que... je
> veux... afin de...*, avec pour chaque spécification un **Contexte** dédié, des **Scénarios
> d'utilisation** (chemin nominal + chemins alternatifs/erreur, tous vérifiés dans
> `api/routes/routes.py`) et des **Critères d'acceptation**.

## Contexte et profils utilisateurs

Waterflow s'adresse à des **collectivités territoriales** qui doivent faire analyser la
potabilité de l'eau distribuée et suivre leurs résultats dans le temps. Trois profils utilisent
la plateforme :

| Profil | Qui | Accès |
|---|---|---|
| **Client** | Une collectivité (mairie, syndicat des eaux) | Clé API — périmètre limité à ses propres données |
| **Analyste** | Expert qualité de l'eau | Token Bearer — vue transverse sur tous les prélèvements |
| **Exploitation** | Responsable technique de la plateforme | Token Bearer — supervision système, RGPD, gestion des clients |

---

## US-01 — Déposer des mesures manuelles et obtenir une prédiction

**En tant que** client, **je veux** saisir directement les 9 mesures physico-chimiques d'un
prélèvement, **afin d'**obtenir immédiatement un verdict de potabilité sans passer par une
fiche papier.

**Contexte** : le client dispose déjà des 9 valeurs numériques (analyse réalisée en interne ou
par un laboratoire tiers dont il ressaisit les résultats) et veut un verdict immédiat, sans
attendre un traitement OCR ni une intervention humaine. Précondition : le client possède une
clé API active.

**Scénarios d'utilisation** :
- *Nominal* : le client envoie `POST /ingest/manual` avec les 9 valeurs complètes et valides
  (pH, dureté, solides dissous, chloramines, sulfates, conductivité, carbone organique,
  trihalométhanes, turbidité) → le prélèvement et la prédiction sont enregistrés, réponse
  `201` avec `potable`/`label`/`probability`.
- *Alternatif — mesure invalide* : une valeur manquante ou non numérique → `run_prediction()`
  lève une erreur *avant* tout enregistrement, réponse `400` avec le détail du champ en cause
  ; rien n'est stocké en base.
- *Alternatif — non authentifié* : requête sans clé API valide (`X-API-Key` absente ou
  inconnue) → `401`, aucun traitement.

**Critères d'acceptation** :
- La requête sans clé API valide est rejetée (401).
- Une mesure manquante ou non numérique renvoie une erreur 400 explicite.
- La réponse contient la prédiction (`potable`/`non potable`), la probabilité et la
  version du modèle utilisée.
- Le formulaire web associé respecte les critères RGAA (labels associés aux champs,
  messages d'erreur annoncés via `aria-live`).

## US-02 — Déposer une fiche labo scannée et obtenir la potabilité (OCR + prédiction)

**En tant que** client, **je veux** envoyer une photo ou un scan de la fiche laboratoire,
**afin de** ne pas ressaisir manuellement les valeurs.

**Contexte** : le client reçoit ses résultats sous forme de fiche papier ou PDF d'un
laboratoire externe et n'a pas les valeurs sous forme numérique exploitable — la ressaisie
manuelle serait source d'erreurs de transcription. Précondition : au moins une clé OCR
(`OCR_SPACE_API_KEY` ou `ANTHROPIC_API_KEY`) est configurée côté plateforme.

**Scénarios d'utilisation** :
- *Nominal* : upload d'un PDF/image lisible et complet via `POST /ingest/ocr-and-predict` →
  OCR.space extrait les 9 mesures, la prédiction est calculée, réponse `201` avec
  `prediction_possible: true`.
- *Alternatif — OCR.space indisponible* : bascule automatique et transparente vers Claude
  Vision (fallback), sans intervention ni nouvelle action du client (cf. `docs/incident.md`
  pour le scénario d'incident détaillé).
- *Alternatif — extraction incomplète* : certaines mesures ne sont pas lisibles sur la fiche →
  le prélèvement est tout de même archivé, `prediction_possible: false`, `prediction_error`
  détaille les champs manquants (pas de prédiction hasardeuse sur des données partielles).
- *Alternatif — fichier rejeté* : type MIME non supporté ou taille supérieure à
  `MAX_UPLOAD_MB` → `400`, rejeté avant tout appel OCR.

**Critères d'acceptation** :
- L'OCR extrait les 9 features via OCR.space (service primaire).
- En cas d'échec ou d'indisponibilité d'OCR.space, un relais automatique vers Claude
  Vision est déclenché (fallback), sans intervention du client.
- Si les mesures extraites sont incomplètes, le prélèvement est tout de même archivé,
  avec `prediction_possible: false` et le détail des champs manquants.
- Taille de fichier limitée (`MAX_UPLOAD_MB`), rejet explicite au-delà.

## US-03 — Déposer une fiche labo pour simple archivage

**En tant que** client, **je veux** pouvoir déposer une fiche labo même incomplète,
**afin de** conserver une trace de tous mes prélèvements, même ceux qui ne peuvent pas
être exploités par le modèle.

**Contexte** : certaines fiches sont trop dégradées ou partielles pour espérer une prédiction
fiable, mais la collectivité a une obligation de traçabilité de tous ses prélèvements
(exploitables ou non) — d'où un point d'entrée distinct de US-02, qui ne déclenche
volontairement aucune prédiction.

**Scénarios d'utilisation** :
- *Nominal* : upload via `POST /ingest/ocr` → extraction et stockage du prélèvement et des
  mesures OCR (même partielles), `201`, **aucune prédiction n'est calculée** (à la différence
  de `/ingest/ocr-and-predict`).
- *Alternatif — échec total de l'OCR* : extraction impossible (service indisponible et
  fallback également en échec) → `503`, rien n'est stocké — contrairement au cas de mesures
  *partiellement* lisibles, qui lui est bien archivé.

**Critères d'acceptation** : le prélèvement et les mesures OCR (même partielles) sont
stockés ; aucune prédiction n'est calculée.

## US-04 — Consulter l'historique de mes prélèvements et résultats

**En tant que** client, **je veux** lister mes prélèvements passés et leurs résultats,
**afin de** suivre l'évolution de la qualité de l'eau dans le temps.

**Contexte** : une collectivité a une obligation de suivi périodique de la qualité de l'eau
distribuée et doit pouvoir présenter un historique (audit interne, réunion du conseil
municipal, contrôle sanitaire) sans dépendre d'un export manuel demandé à un tiers.

**Scénarios d'utilisation** :
- *Nominal* : `GET /me/prelevements` (paginé, triable par date) pour la liste, puis
  `GET /me/prelevements/<id>` pour le détail d'un prélèvement précis.
- *Alternatif — prélèvement d'un autre client* : identifiant valide mais appartenant à une
  autre collectivité → `403` (« Accès refusé »), distinct du `404` renvoyé si l'identifiant
  n'existe simplement pas — la plateforme ne confirme ni n'infirme l'existence d'un
  prélèvement hors périmètre.

**Critères d'acceptation** :
- Un client ne peut jamais voir les prélèvements d'un autre client (filtre strict par
  `client_id` côté serveur).
- La liste est paginée et triable par date.
- L'interface web affiche les résultats sous forme de tableau accessible au clavier
  (navigation par tabulation, focus visible).

## US-05 — Exercer mes droits RGPD

**En tant que** client, **je veux** consulter et pouvoir effacer mes données personnelles,
**afin d'**exercer mes droits d'accès (art. 15) et à l'effacement (art. 17) du RGPD.

**Contexte** : la collectivité (personne morale, mais dont les champs `denomination`/`adresse`
peuvent identifier un contact) souhaite soit vérifier ce que la plateforme détient sur elle,
soit mettre fin à la relation et faire valoir son droit à l'effacement — tout en respectant
l'obligation légale de traçabilité des prélèvements déjà réalisés.

**Scénarios d'utilisation** :
- *Nominal (accès)* : `GET /me/rgpd` → export de toutes les données personnelles détenues.
- *Nominal (effacement, en 2 étapes)* : `DELETE /me/rgpd` **sans** `{"confirmer": true}` →
  `400`, message explicite demandant la confirmation ; nouvel appel **avec**
  `{"confirmer": true}` → anonymisation effective (`denomination`/`adresse` écrasées, clé API
  révoquée, compte désactivé), `200`. Ce garde-fou en deux temps empêche un effacement
  accidentel déclenché par une requête automatisée mal formée.
- *Alternatif* : les prélèvements déjà réalisés ne sont **pas** supprimés mais conservés sous
  forme anonymisée (obligation légale de traçabilité), conformément au message retourné par
  l'API à l'issue de l'effacement.

**Critères d'acceptation** :
- L'export liste toutes les données personnelles détenues (dénomination, adresse,
  historique).
- La suppression est irréversible, confirmée explicitement, et journalisée dans
  `audit_logs`.

## US-06 — Gérer les comptes clients (création, clé API)

**En tant qu'**exploitant, **je veux** créer des comptes clients et générer/régénérer leur
clé API, **afin de** contrôler les accès à la plateforme.

**Contexte** : l'onboarding d'une nouvelle collectivité (ou la rotation d'une clé compromise
ou perdue par un client) est une opération administrative que tout expert doit pouvoir
réaliser, sans dépendre exclusivement du responsable d'exploitation — d'où un accès ouvert
« tout expert » plutôt que restreint au seul rôle `exploit`.

**Scénarios d'utilisation** :
- *Nominal (création)* : `POST /admin/clients` avec les informations de la collectivité →
  compte créé, `201`.
- *Nominal (rotation de clé)* : `POST /admin/clients/<id>/apikey` → nouvelle clé générée
  (`secrets.token_urlsafe(32)`), l'ancienne est immédiatement révoquée, la clé brute n'est
  retournée **qu'une seule fois** dans la réponse.
- *Alternatif — client désactivé* : tentative de régénération de clé sur un compte
  `actif=false` → `409` (« Client désactivé. Réactivez-le d'abord... »), la réactivation via
  `PUT /admin/clients/<id>` est un préalable explicite.
- *Alternatif — client introuvable* : identifiant inconnu → `404`.

**Critères d'acceptation** :
- La clé générée (`secrets.token_urlsafe(32)`) n'est affichée qu'une seule fois à la
  création/régénération ; seul un hash SHA-256 est conservé en base.
- Seul un token expert valide (rôle indifférent) peut accéder à ces routes.
- L'onglet "Clients" de l'interface expose un formulaire de création et un bouton
  "Nouvelle clé", avec confirmation avant régénération (perte de l'ancienne clé).

## US-07 — Consulter tous les prélèvements avec filtres (vue analyste)

**En tant qu'**analyste, **je veux** consulter l'ensemble des prélèvements de toutes les
collectivités avec des filtres (client, source, dates), **afin de** mener des
investigations qualité transverses.

**Contexte** : l'analyste qualité de l'eau doit pouvoir croiser les résultats de plusieurs
collectivités (ex. repérer une dérive géographique ou saisonnière) — un accès restreint à un
seul client (comme la vue Client) ne le permettrait pas ; d'où un rôle dédié avec vue
transverse.

**Scénarios d'utilisation** :
- *Nominal* : `GET /analyste/prelevements?client_id=...&source=...&date_from=...&date_to=...`
  avec un ou plusieurs filtres combinés (ET logique) → liste filtrée.
- *Nominal (détail enrichi)* : `GET /analyste/prelevements/<id>` → inclut la sortie OCR
  brute, contrairement à `GET /me/prelevements/<id>` côté client.
- *Alternatif — rôle insuffisant* : un token client (clé API) tente d'accéder à cette route
  → `401` (authentification experte requise, pas seulement une clé client).

**Critères d'acceptation** :
- Les filtres combinés fonctionnent (ET logique).
- Le détail d'un prélèvement (`GET /analyste/prelevements/<id>`) inclut la sortie OCR
  brute, contrairement à la vue client.
- **Statut UI** : les filtres sont exposés côté API et intégrés à l'interface web ;
  reste à vérifier lors de la recette finale que les 4 filtres (client, source, date
  début, date fin) sont bien tous exposés dans le formulaire (point de vigilance
  identifié en revue interne).

## US-08 — Visualiser un dashboard de KPIs qualité

**En tant qu'**analyste, **je veux** un tableau de bord synthétique (taux de potabilité,
moyennes physico-chimiques, nombre de clients actifs), **afin de** piloter la qualité sans
extraire manuellement les données.

**Contexte** : sans ce dashboard, l'analyste devrait recalculer ces indicateurs à la main à
partir de la liste brute des prélèvements (US-07) à chaque point de suivi — le dashboard
mutualise ce calcul côté serveur pour éviter une charge répétitive et des écarts de méthode
entre analystes.

**Scénarios d'utilisation** :
- *Nominal* : `GET /analyste/dashboard` → indicateurs recalculés à la demande (taux de
  potabilité, moyennes physico-chimiques, nombre de clients actifs), affichés en cartes
  chiffrées + graphiques dans l'onglet Dashboard de l'interface.
- *Alternatif — aucune donnée* : aucun prélèvement en base (installation fraîche) → les
  indicateurs renvoient des valeurs nulles/vides plutôt qu'une erreur, l'interface reste
  utilisable.

**Critères d'acceptation** : les indicateurs se recalculent à la demande (pas de cache
périmé), et le dashboard web les affiche en cartes chiffrées + graphiques.

## US-09 — Surveiller la dérive du modèle en production

**En tant que** responsable d'exploitation, **je veux** être alerté si les données reçues
en production s'écartent des données d'entraînement, **afin d'**anticiper un
ré-entraînement avant que le modèle ne se dégrade silencieusement.

**Contexte** : un modèle ML entraîné sur un jeu de données figé peut se dégrader
silencieusement si la distribution des mesures reçues en production dérive (nouvelle zone
géographique raccordée, changement de méthode de mesure d'un laboratoire partenaire...) —
sans surveillance active, cette dérive ne serait détectée qu'au moment où les prédictions
deviennent visiblement mauvaises, trop tard pour anticiper.

**Scénarios d'utilisation** :
- *Nominal* : `GET /exploitation/monitoring?window_days=30` (ou onglet "Monitoring" côté UI)
  → score PSI par variable (9 features), niveau `ok`/`warn`/`critical`, alertes de confiance
  et de dérive du taux de potabilité.
- *Alternatif — volumétrie insuffisante* : moins de 50 échantillons sur la fenêtre demandée
  (`MIN_SAMPLES_PSI`) → niveau `insufficient_data` par variable plutôt qu'un score PSI
  potentiellement trompeur sur un trop petit échantillon.
- *Alternatif — fenêtre hors bornes* : `window_days` demandé au-delà de 365 → plafonné
  automatiquement à 365 (`min(365, max(1, ...))`), pas d'erreur.

**Critères d'acceptation** :
- Un score de dérive (PSI) est calculé par variable, avec 3 niveaux (`ok` / `warn` /
  `critical`), et `insufficient_data` en dessous de 50 échantillons pour éviter les
  faux positifs.
- Une alerte est levée si la confiance moyenne des prédictions descend sous 65 % ou si
  le taux de potabilité dévie de plus de 15 points par rapport à la baseline
  d'entraînement.

## US-10 — Consulter les métriques système et le journal d'audit RGPD

**En tant que** responsable d'exploitation, **je veux** consulter les métriques de
performance de l'API et le journal des accès RGPD, **afin de** garantir la disponibilité
du service et la conformité réglementaire.

**Contexte** : le responsable d'exploitation porte la responsabilité opérationnelle (SLA de
disponibilité) et réglementaire (traçabilité des accès aux données personnelles, exigée par
le RGPD) de la plateforme — ces deux besoins sont distincts de ceux de l'analyste (qualité de
l'eau) et justifient un rôle `exploit` séparé, strictement plus restreint dans sa
population mais strictement plus large dans ses accès (super-rôle, cf. `require_expert`).

**Scénarios d'utilisation** :
- *Nominal (métriques)* : `GET /exploitation/metrics` → p50/p95 de latence et taux d'erreur
  par route, calculés depuis `request_metrics`.
- *Nominal (audit)* : `GET /exploitation/audit` → journal `audit_logs` (IP pseudonymisée),
  pour investiguer un accès suspect ou répondre à une demande de contrôle.
- *Alternatif — rôle insuffisant* : un token `analyste` (pas `exploit`) tente d'accéder à
  l'une de ces deux routes → `403`.

**Critères d'acceptation** : les deux endpoints sont accessibles uniquement au rôle
`exploit`. **Statut UI** : `/exploitation/metrics` est intégré à l'onglet Monitoring ;
l'exposition de `/exploitation/audit` dans un onglet dédié de l'interface reste à
planifier (inscrit au backlog produit).

---

## Synthèse accessibilité

Les objectifs d'accessibilité sont formulés selon le référentiel **RGAA** (Référentiel
Général d'Amélioration de l'Accessibilité) et intégrés directement aux critères
d'acceptation ci-dessus plutôt que traités à part : rôles ARIA sur les composants
interactifs (`role="tab"`, `aria-selected`, `aria-controls`), zones live pour les messages
d'erreur (`aria-live`), focus clavier visible sur tous les contrôles interactifs.

# Waterflow — User Stories

> Document reconstruit à partir de l'application existante (routes, rôles et comportements
> implémentés) pour formaliser a posteriori le besoin métier. Formalisme : *En tant que... je
> veux... afin de...* avec critères d'acceptation.

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

- **Scénario** : le client envoie `POST /ingest/manual` avec les 9 valeurs (pH, dureté,
  solides dissous, chloramines, sulfates, conductivité, carbone organique,
  trihalométhanes, turbidité).
- **Critères d'acceptation** :
  - La requête sans clé API valide est rejetée (401).
  - Une mesure manquante ou non numérique renvoie une erreur 400 explicite.
  - La réponse contient la prédiction (`potable`/`non potable`), la probabilité et la
    version du modèle utilisée.
  - Le formulaire web associé respecte les critères RGAA (labels associés aux champs,
    messages d'erreur annoncés via `aria-live`).

## US-02 — Déposer une fiche labo scannée et obtenir la potabilité (OCR + prédiction)

**En tant que** client, **je veux** envoyer une photo ou un scan de la fiche laboratoire,
**afin de** ne pas ressaisir manuellement les valeurs.

- **Scénario** : `POST /ingest/ocr-and-predict` avec un fichier image/PDF.
- **Critères d'acceptation** :
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

- **Scénario** : `POST /ingest/ocr` (sans déclenchement de la prédiction).
- **Critères d'acceptation** : le prélèvement et les mesures OCR (même partielles) sont
  stockés ; aucune prédiction n'est calculée.

## US-04 — Consulter l'historique de mes prélèvements et résultats

**En tant que** client, **je veux** lister mes prélèvements passés et leurs résultats,
**afin de** suivre l'évolution de la qualité de l'eau dans le temps.

- **Scénario** : `GET /me/prelevements` (paginé), `GET /me/prelevements/<id>`,
  `GET /me/resultats`.
- **Critères d'acceptation** :
  - Un client ne peut jamais voir les prélèvements d'un autre client (filtre strict par
    `client_id` côté serveur).
  - La liste est paginée et triable par date.
  - L'interface web affiche les résultats sous forme de tableau accessible au clavier
    (navigation par tabulation, focus visible).

## US-05 — Exercer mes droits RGPD

**En tant que** client, **je veux** consulter et pouvoir effacer mes données personnelles,
**afin d'**exercer mes droits d'accès (art. 15) et à l'effacement (art. 17) du RGPD.

- **Scénario** : `GET /me/rgpd` (export des données détenues), `DELETE /me/rgpd`
  (anonymisation irréversible avec confirmation).
- **Critères d'acceptation** :
  - L'export liste toutes les données personnelles détenues (dénomination, adresse,
    historique).
  - La suppression est irréversible, confirmée explicitement, et journalisée dans
    `audit_logs`.

## US-06 — Gérer les comptes clients (création, clé API)

**En tant qu'**exploitant, **je veux** créer des comptes clients et générer/régénérer leur
clé API, **afin de** contrôler les accès à la plateforme.

- **Scénario** : `POST /admin/clients`, `GET /admin/clients(/<id>)`, `PUT
  /admin/clients/<id>`, `POST /admin/clients/<id>/apikey`.
- **Critères d'acceptation** :
  - La clé générée (`secrets.token_urlsafe(32)`) n'est affichée qu'une seule fois à la
    création/régénération ; seul un hash SHA-256 est conservé en base.
  - Seul un token expert valide (rôle indifférent) peut accéder à ces routes.
  - L'onglet "Clients" de l'interface expose un formulaire de création et un bouton
    "Nouvelle clé", avec confirmation avant régénération (perte de l'ancienne clé).

## US-07 — Consulter tous les prélèvements avec filtres (vue analyste)

**En tant qu'**analyste, **je veux** consulter l'ensemble des prélèvements de toutes les
collectivités avec des filtres (client, source, dates), **afin de** mener des
investigations qualité transverses.

- **Scénario** : `GET /analyste/prelevements?client_id=...&source=...&date_from=...&date_to=...`
- **Critères d'acceptation** :
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

- **Scénario** : `GET /analyste/dashboard`.
- **Critères d'acceptation** : les indicateurs se recalculent à la demande (pas de cache
  périmé), et le dashboard web les affiche en cartes chiffrées + graphiques.

## US-09 — Surveiller la dérive du modèle en production

**En tant que** responsable d'exploitation, **je veux** être alerté si les données reçues
en production s'écartent des données d'entraînement, **afin d'**anticiper un
ré-entraînement avant que le modèle ne se dégrade silencieusement.

- **Scénario** : `GET /exploitation/monitoring`, onglet "Monitoring" du dashboard expert.
- **Critères d'acceptation** :
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

- **Scénario** : `GET /exploitation/metrics` (p50/p95, taux d'erreur par route),
  `GET /exploitation/audit` (journal `audit_logs`, IP pseudonymisée).
- **Critères d'acceptation** : les deux endpoints sont accessibles uniquement au rôle
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

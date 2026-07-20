# Waterflow — Documentation RGPD

> Document reconstruit à partir de l'implémentation existante (modèles de données,
> routes, middleware d'authentification et d'audit) pour formaliser a posteriori la
> conformité RGPD du traitement.

## 1. Périmètre et responsable de traitement

Waterflow traite des données pour le compte de collectivités territoriales
(mairies, syndicats des eaux) dans le cadre du suivi de la potabilité de l'eau
distribuée. Le responsable de traitement est l'exploitant de la plateforme
Waterflow ; les collectivités clientes sont les destinataires de leurs propres
données et, le cas échéant, responsables conjoints pour les données qu'elles
soumettent (mesures, fiches labo).

**Contact délégué à la protection des données (DPO)** : dpo@waterflow.example.com
(adresse de contact exposée aux clients via `GET /me/rgpd`, cf. §5).

## 2. Registre des traitements

| Traitement | Finalité | Données concernées | Base légale |
|---|---|---|---|
| Gestion des comptes clients | Authentifier les collectivités et restreindre l'accès à leurs propres données | `id_client`, `denomination`, `adresse`, `api_key_hash` | Exécution du contrat de service |
| Dépôt et suivi des prélèvements | Assurer la traçabilité des analyses d'eau et calculer la prédiction de potabilité | Mesures physico-chimiques, fichiers de fiches labo, texte OCR brut | Exécution du contrat de service |
| Journalisation des accès (audit) | Assurer la sécurité, la traçabilité et permettre la détection d'incidents | `actor_type`, `actor_id`, IP pseudonymisée, action, horodatage | Intérêt légitime (sécurité du système d'information) |
| Métriques de performance | Superviser la disponibilité et la performance du service | Route, méthode, code retour, durée — aucune donnée personnelle directe | Intérêt légitime |
| Extraction OCR via services tiers | Convertir une fiche labo scannée en données structurées | Contenu du fichier déposé (peut inclure un nom de préleveur ou une adresse de site) | Exécution du contrat de service |

## 3. Classification des données personnelles par table

Le modèle de données (`api/models/db.py`) identifie les tables suivantes comme
porteuses de données personnelles, avec le niveau de sensibilité associé :

| Table | Champ | Nature | Mesure de protection |
|---|---|---|---|
| `clients` | `denomination`, `adresse` | Identification d'une personne morale | Minimisation : uniquement ce qui est nécessaire au contrat |
| `clients` | `api_key_hash` | Secret d'authentification | Jamais stocké en clair — hash SHA-256 uniquement (`Client.hash_key`) |
| `clients` | `api_key_hint` | Fragment de clé (4 premiers caractères) | Utilisé uniquement pour l'identification en support, non exploitable seul |
| `prelevements` | `ocr_raw_text`, `ocr_warnings` | Peut contenir des mentions manuscrites identifiantes (nom d'un préleveur) | Accessible uniquement au rôle `analyste`/`exploit`, jamais à un autre client |
| `audit_logs` | `ip_address` | Donnée personnelle indirecte | Pseudonymisée avant stockage (dernier octet IPv4 masqué, cf. §4) |
| `audit_logs` | `actor_id` | Identifiant client ou login expert | Nécessaire à la finalité de traçabilité, non exploitable pour un profilage |

Aucune donnée de santé ou donnée biométrique n'est collectée : les mesures
physico-chimiques portent sur l'eau distribuée, non sur des personnes.

## 4. Mesures de sécurité techniques

### 4.1 Authentification

- Les clés API clients ne sont **jamais stockées en clair** : seul un hash
  SHA-256 est conservé en base (`Client.set_api_key` / `Client.verify_key`).
- La comparaison de clé utilise `hashlib.compare_digest` (temps constant),
  une protection contre les attaques par mesure de temps.
- Les comptes experts utilisent des tokens statiques configurés côté serveur
  (`EXPERT_TOKENS`), jamais transmis ni stockés côté client.

### 4.2 Pseudonymisation des adresses IP

Chaque entrée du journal d'audit pseudonymise l'adresse IP de la requête avant
stockage, en masquant le dernier octet (IPv4) ou le dernier segment (IPv6) :

```python
def _pseudo_ip(ip: str | None) -> str:
    """Pseudonymise l'IP : masque le dernier octet IPv4."""
    if not ip:
        return "unknown"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return ip[:ip.rfind(":") + 1] + "xxx" if ":" in ip else ip
```

Cette fonction est appelée systématiquement par `_write_audit()`, point d'entrée
unique de toute écriture dans `audit_logs` — aucune route ne peut donc
contourner la pseudonymisation.

### 4.3 Séparation stricte des périmètres

Le middleware d'authentification (`require_client_key`) filtre systématiquement
les requêtes par `client_id`, rendant structurellement impossible pour un
client d'accéder aux données d'un autre — la séparation est appliquée au niveau
du code d'accès aux données, pas seulement au niveau de l'interface.

### 4.4 Journal d'audit immuable

La table `audit_logs` ne dispose d'aucune route de modification ou de
suppression : chaque accès (consultation, dépôt, modification) est journalisé
via `log_audit()` et conservé tel quel, garantissant l'intégrité de la
traçabilité en cas d'investigation.

## 5. Droits des personnes concernées

### 5.1 Droit d'accès et d'information (art. 13-15)

Route : `GET /me/rgpd` (authentification par clé API du client concerné).

La réponse inclut :
- les données personnelles détenues (identifiant, dénomination, adresse, dates
  de création de compte et de génération de clé) ;
- le nombre de prélèvements et de prédictions associés au compte ;
- l'historique des 50 derniers accès au compte (date, action, IP pseudonymisée,
  statut) ;
- les règles de conservation applicables (§6) ;
- le détail des droits disponibles et le contact du DPO.

### 5.2 Droit à l'effacement (art. 17)

Route : `DELETE /me/rgpd`, avec confirmation explicite obligatoire
(`{"confirmer": true}` dans le corps de la requête) pour éviter toute
suppression accidentelle par un appel automatisé mal formé.

Effet : anonymisation irréversible du compte —

```python
c.denomination  = f"[ANONYMISÉ-{c.id_client}]"
c.adresse       = "[ANONYMISÉ]"
c.api_key_hash  = None
c.api_key_hint  = None
c.actif         = False
c.anonymised_at = utcnow()
```

Les prélèvements et mesures associés sont **conservés sous forme
anonymisée** plutôt que supprimés physiquement — un compromis assumé entre le
droit à l'effacement et les obligations de traçabilité réglementaire propres
au secteur de l'eau potable (justification à faire valoir en cas de contrôle).

### 5.3 Droit de rectification

Non exposé en libre-service à ce stade : une collectivité souhaitant corriger
sa dénomination ou son adresse doit contacter un administrateur, qui utilise
`PUT /admin/clients/<id>`. **Limite identifiée** : l'ajout d'une route
`PUT /me` en libre-service pour les champs non sensibles constituerait une
amélioration naturelle.

### 5.4 Droit à la portabilité

Couvert indirectement via `GET /me/prelevements`, qui permet à un client
d'exporter l'intégralité de son historique de prélèvements dans un format
structuré (JSON) réutilisable.

## 6. Durées de conservation

| Donnée | Durée | Mécanisme |
|---|---|---|
| Prélèvements et mesures | Conservés sans limitation tant que le compte est actif | Aucune purge automatique — conservation liée à l'activité du compte |
| Journaux d'accès (`audit_logs`) | 12 mois glissants | Purge à prévoir (non encore automatisée, cf. limite ci-dessous) |
| Métriques de performance (`request_metrics`) | Agrégées et anonymisées après 90 jours | Idem |
| Clé API | Jamais stockée en clair | Hash SHA-256 uniquement |

**Limite identifiée** : la purge automatique des `audit_logs` au-delà de 12
mois et des `request_metrics` au-delà de 90 jours est documentée comme règle
mais n'est pas encore implémentée sous forme de tâche planifiée (cron / job
périodique). Il s'agit d'une action prioritaire à réaliser avant une montée en
charge en production, actuellement inscrite au backlog produit du projet
(cf. rapport E4, tableau Kanban).

## 7. Sous-traitants et transferts vers des tiers

Le module d'extraction OCR (`api/services/ocr_service.py`, documenté en détail
dans le rapport E2) transmet le contenu des fichiers déposés par les clients à
deux sous-traitants potentiels :

| Sous-traitant | Donnée transmise | Finalité | Point de vigilance |
|---|---|---|---|
| OCR.space | Fichier image/PDF de la fiche labo | Extraction de texte | Localisation des serveurs de traitement non garantie identique entre les deux fournisseurs — point à réexaminer avant un passage à l'échelle (cf. rapport E2, §2.6) |
| Anthropic (Claude Vision) | Fichier image/PDF de la fiche labo (fallback uniquement) | Extraction sémantique structurée | Utilisé uniquement en cas d'échec du service primaire, donc de façon minoritaire |

Aucune donnée n'est transmise à ces services au-delà du strict document déposé
par le client pour le traitement en cours ; aucun stockage prolongé côté
Waterflow du contenu transmis à ces tiers n'est effectué au-delà du résultat
structuré (JSON) retourné et persisté en base.

## 8. Procédure en cas de violation de données

En l'état actuel du projet (MVP), aucune procédure formalisée de notification
de violation (art. 33-34 RGPD) n'est encore rédigée. Le journal d'audit
immuable (§4.4) et les métriques de performance constituent la base
technique nécessaire pour qualifier rapidement le périmètre d'un incident
éventuel (quels comptes concernés, quelle fenêtre temporelle), mais la
procédure de notification à la CNIL et aux personnes concernées reste à
formaliser — **action prioritaire avant une mise en production réelle**.

## 9. Limites identifiées et pistes d'amélioration

- Purge automatique des journaux d'audit et métriques non encore implémentée
  (§6).
- Procédure de notification de violation de données à rédiger (§8).
- Droit de rectification non exposé en libre-service côté client (§5.3).
- La localisation géographique des sous-traitants OCR n'est pas garantie
  contractuellement à ce stade (§7) — à formaliser via un accord de
  sous-traitance (art. 28 RGPD) avant un usage en production avec des volumes
  de données personnelles significatifs.

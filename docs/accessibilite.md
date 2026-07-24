# Waterflow — Accessibilité pour toutes les parties prenantes du projet

> Document de preuve : justifie le choix de l'outil de restitution au regard
> de l'accessibilité pour l'ensemble des profils utilisateurs du projet, puis
> vérifie — critère par critère, avec référence exacte au code — que cette
> intention est réellement appliquée. Construit par vérification directe du
> code (pas par relecture de la seule documentation), les écarts trouvés sont
> listés en transparence, avec leur statut (corrigé / mineur / hors périmètre).

## 1. Les parties prenantes du projet

D'après `docs/user_stories.md` §"Contexte et profils utilisateurs" :

| Profil | Qui | Interaction principale |
|---|---|---|
| **Client** | Collectivité (mairie, syndicat des eaux) | Dépôt de mesures/fiches labo, consultation de ses résultats |
| **Analyste** | Expert qualité de l'eau | Vue transverse, dashboard, filtres |
| **Exploitation** | Responsable technique | Supervision système, monitoring, gestion des comptes |
| *(Consommateur API externe)* | Développeur intégrant la plateforme | Documentation OpenAPI (`/apidocs`) |

## 2. Le choix de l'outil de restitution — et pourquoi il sert l'accessibilité pour tous

**Choix fait** : une **interface web unique** (`templates/index.html`, HTML/JS/Tailwind), servie par la même application Flask que l'API, avec une vue client et une vue experte dans le même document — plutôt que, par exemple, un outil de BI tiers (Metabase, PowerBI) pour les experts et une appli séparée pour les clients.

**Pourquoi ce choix sert l'accessibilité de toutes les parties prenantes à la fois** :
- Un seul code base à auditer et corriger, plutôt que la fragmentation de l'effort RGAA sur plusieurs outils hétérogènes (dont certains, comme un outil de BI propriétaire, échapperaient totalement au contrôle du projet).
- Les mêmes primitives d'accessibilité (skip-link, rôles ARIA, focus visible) bénéficient mécaniquement aux deux vues (client et experte), car elles partagent la même structure de page et les mêmes styles.
- Pour le consommateur API externe, le choix d'une documentation **OpenAPI standard** (`swagger.yaml` + Swagger UI via Flasgger) plutôt qu'un wiki interne non structuré permet de s'appuyer sur les efforts d'accessibilité déjà fournis par l'écosystème Swagger UI (composant tiers, non ré-audité indépendamment dans ce projet — voir limite §5).

Cette décision est documentée comme volontaire dans `docs/architecture.md` (*"Interface web unique (vue client + vue expert), conforme RGAA"*) et dans la synthèse de `docs/user_stories.md`.

## 3. Matrice parties prenantes × critères RGAA × preuve code

| Partie prenante | Fonctionnalité | Critère RGAA visé | Preuve dans le code | Statut |
|---|---|---|---|---|
| Toutes | Navigation générale | Lien d'évitement (RGAA 12.7) | `.skip-link` → `#main-content`, `templates/index.html` L20-27, 142 | ✅ |
| Toutes | Connexion | Labels associés, erreurs annoncées | `<label for="inp-key">`/`for="inp-tok"`, `#login-err` `role="alert" aria-live="assertive"` | ✅ |
| Toutes | Icônes décoratives | Alternative textuelle (RGAA 1.1/1.2) | `aria-hidden="true"` sur les emojis (15+ occurrences) | ✅ |
| Analyste / Exploitation | Onglets de navigation | Composant onglet accessible (RGAA 7/11) | `role="tablist"`/`role="tab"`/`role="tabpanel"`, `aria-selected`, `aria-controls` | ✅ |
| Exploitation | Onglet Monitoring | Visible uniquement pour le rôle habilité | `showTab()` masque l'onglet si `role !== 'exploit'`, recalculé à chaque changement d'onglet | ✅ (corrigé — bug de réinitialisation trouvé et résolu, cf. échanges précédents) |
| **Client** | **US-01 — formulaire d'analyse manuelle** | **Labels associés aux champs, erreurs via `aria-live`** | `buildManualForm()` : `<label for="mf-${f.k}">`, `#manual-res`/`#ocr-res` `role="alert" aria-live="assertive"` | ✅ **corrigé** — labels non associés et zones sans `aria-live` à l'origine (contredisait US-01), corrigés et vérifiés dans un vrai navigateur |
| Client | US-04 — historique des prélèvements | Tableau accessible au clavier | `prevTable()` : vrai `<table>`/`<thead>`/`<tbody>` sémantique, pas de widget custom | ✅ |
| Client | Upload OCR — résultat | Mesures extraites lisibles, pas seulement le verdict | `renderExtractedMesures()` : affiche les 9 mesures + avertissements OCR | ✅ (ajouté suite à une demande explicite, testé avec le vrai modèle) |
| *(Consommateur API)* | Documentation OpenAPI | — | Swagger UI (Flasgger), composant tiers | ⚠️ non audité indépendamment (voir §5) |

## 4. Comment reproduire cette vérification

```bash
# 1. Navigation clavier pure (sans souris) : Tab / Shift+Tab / Entrée / flèches
#    - Le premier Tab doit révéler le lien d'évitement
#    - Les onglets experts doivent s'activer au clavier
#    - Un analyste connecté ne doit jamais voir l'onglet "Monitoring"

# 2. Vérification programmatique des labels (exemple Playwright, cf. session) :
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('http://localhost:8080')
    # ... login, puis :
    for lbl in page.query_selector_all('#manual-fields label'):
        for_attr = lbl.get_attribute('for')
        assert for_attr and page.query_selector(f'#{for_attr}')
    browser.close()
"

# 3. Audit automatisé tiers (preuve objective, non auto-déclarée) :
#    Chrome DevTools > Lighthouse > Accessibility, ou extension axe DevTools,
#    sur http://localhost:8080 (vue client) et vue experte.
```

## 5. Limites et écarts connus

1. **3 boutons "Actualiser"** (`templates/index.html`, vues client/analyste/exploitation) n'ont ni `focus:outline-none` ni `focus:ring` explicite — contrairement au reste de l'interface. Ce n'est **pas** un défaut fonctionnel : n'ayant pas retiré l'outline navigateur par défaut, ces boutons restent visibles au focus clavier (contour natif du navigateur) — c'est une **incohérence visuelle mineure** (style natif vs anneau bleu personnalisé ailleurs), pas une violation RGAA.
2. **Swagger UI** (`/apidocs`, bibliothèque tierce Flasgger) n'a pas été auditée indépendamment dans le cadre de ce projet — son accessibilité dépend entièrement du composant amont, hors du code de Waterflow.
3. Cette matrice couvre les fonctionnalités **vérifiées au cours des échanges de cette session** (formulaires, onglets, tableaux, alertes) — pas un audit RGAA complet et exhaustif (106 critères du référentiel officiel), qui nécessiterait un outil dédié et une revue méthodique critère par critère.
4. Un écart réel a été trouvé puis corrigé : le formulaire d'analyse manuelle contredisait l'acceptation critère de US-01 (labels non associés, pas d'`aria-live`) — corrigé, testé dans un vrai navigateur (voir §3, ligne en gras).

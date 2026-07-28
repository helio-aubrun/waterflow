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

## 3. Matrice parties prenantes × critères de standard × preuve code

> Chaque référence RGAA/WCAG ci-dessous a été **vérifiée contre le
> référentiel officiel** (RGAA 4.1.2, portail accessibilité.public.lu — pas
> citée de mémoire) avant d'être inscrite ; une citation antérieure erronée
> a été trouvée et corrigée à cette occasion (cf. note sous le tableau). Les
> deux lignes qui ne correspondent à aucun critère de standard identifiable
> sont marquées comme telles plutôt que rattachées artificiellement à RGAA.

| Partie prenante | Fonctionnalité | Critère de standard visé | Preuve dans le code | Statut |
|---|---|---|---|---|
| Toutes | Navigation générale | Lien d'évitement (**RGAA 12.7**) | `.skip-link` → `#main-content`, `templates/index.html` L20-27, 142 | ✅ |
| Toutes | Connexion | Étiquettes associées (**RGAA 11.1** + **11.4**), erreur annoncée (**WCAG 4.1.3** *Status Messages*) | `<label for="inp-key">`/`for="inp-tok"`, `#login-err` `role="alert" aria-live="assertive"` | ✅ |
| Toutes | Icônes décoratives | Alternative textuelle (**RGAA 1.1/1.2**) | `aria-hidden="true"` sur les emojis (15+ occurrences) | ✅ |
| Analyste / Exploitation | Onglets de navigation | Composant script accessible (**RGAA 7.1** rôle pertinent + **7.3** clavier) | `role="tablist"`/`role="tab"`/`role="tabpanel"`, `aria-selected`, `aria-controls` | ✅ *(citation corrigée — précédemment « RGAA 7/11 », la thématique 11 est « Formulaires », sans rapport ; le bon repère est la thématique 7 « Scripts »)* |
| Exploitation | Onglet Monitoring | *(pas un critère d'accessibilité — règle d'autorisation/moindre privilège)* | `showTab()` masque l'onglet si `role !== 'exploit'`, recalculé à chaque changement d'onglet | ✅ (corrigé — bug de réinitialisation trouvé et résolu, cf. échanges précédents) |
| **Client** | **US-01 — formulaire d'analyse manuelle** | **RGAA 11.1 + 11.4** (étiquettes), **WCAG 4.1.3** (erreur via `aria-live`) | `buildManualForm()` : `<label for="mf-${f.k}">`, `#manual-res`/`#ocr-res` `role="alert" aria-live="assertive"` | ✅ **corrigé** — labels non associés et zones sans `aria-live` à l'origine (contredisait US-01), corrigés et vérifiés dans un vrai navigateur |
| Client | US-04 — historique des prélèvements | Structure programmatiquement déterminable (**WCAG 1.3.1** — pas de numéro RGAA précis identifié avec confiance pour ce cas) | `prevTable()` : vrai `<table>`/`<thead>`/`<tbody>` sémantique, pas de widget custom | ✅ |
| Client | Upload OCR — résultat | *(pas un critère d'accessibilité — exigence de complétude du contenu restitué)* | `renderExtractedMesures()` : affiche les 9 mesures + avertissements OCR | ✅ (ajouté suite à une demande explicite, testé avec le vrai modèle) |
| *(Consommateur API)* | Documentation OpenAPI | — | Swagger UI (Flasgger), composant tiers | ⚠️ non audité indépendamment (voir §5) |

**Note sur la citation corrigée** : « RGAA 7/11 » (onglets) avait été
initialement rédigée par association informelle avec les thématiques
« Scripts » et « Formulaires », sans vérification contre le référentiel
officiel — en le vérifiant (recherche + lecture du référentiel RGAA 4.1.2
et du portail accessibilité.public.lu), la thématique 11 s'est révélée
sans rapport avec les composants d'onglets (elle concerne les formulaires).
De même, « RGAA 11.10 » envisagé pour l'accolement étiquette/champ était
incorrect (11.10 concerne le contrôle de saisie) — le bon critère est
**11.4**. Les deux lignes reclassées (Monitoring, OCR) décrivaient des
exigences réelles et déjà correctement implémentées, mais n'étaient pas
des critères d'un standard d'accessibilité au sens strict — les présenter
comme tels aurait été inexact.

## 4. Inventaire technique par critère (occurrences vérifiées dans le code)

Vue complémentaire de la matrice §3 (organisée par partie prenante) :
ici, un critère RGAA/WCAG par ligne, avec l'implémentation exacte et le
nombre d'occurrences **recompté dans le code réel** (`templates/index.html`)
au moment de la rédaction — pas recopié d'une estimation antérieure.

| Critère RGAA/WCAG | Implémentation | Occurrences vérifiées |
|---|---|---|
| Langue de la page (RGAA 8.3) | `<html lang="fr">` | ligne 2 |
| Lien d'évitement (RGAA 12.7 / WCAG 2.4.1) | `.skip-link` → `#main-content`, `<main id="main-content" tabindex="-1">` | lignes 20-21, 27, 142 |
| Icônes décoratives masquées aux lecteurs d'écran (RGAA 1.1/1.2) | `aria-hidden="true"` sur chaque emoji | 15 occurrences |
| Onglets accessibles au clavier (**RGAA 7.1 rôle pertinent + 7.3 clavier**) | `role="tablist"`/`role="tab"`/`role="tabpanel"`, `aria-selected`, `aria-controls` | 2 `tablist`, 8 `tab`, 2 `tabpanel`, 8 `aria-controls` |
| Messages d'erreur annoncés dynamiquement (WCAG 4.1.3) | `role="alert"` + `aria-live="assertive"` sur les zones d'erreur | ligne du bloc `login-err` |
| Fenêtre modale accessible (RGAA 7.1) | `role="dialog"`, `aria-modal="true"`, `aria-labelledby` | ligne du `#modal` |
| Labels de formulaire associés (RGAA 11.1 + 11.4) | `<label for="...">` lié à chaque `<input>` | **13 labels** |
| Indicateur de focus visible au clavier (WCAG 2.4.7) | `focus:ring-2` sur les éléments interactifs | **21 occurrences** |
| Liens ouvrant un nouvel onglet annoncés (RGAA 6.2) | `aria-label="... (ouvre dans un nouvel onglet)"` sur le lien Swagger | présent |

**Écarts corrigés par rapport à un premier inventaire non versionné** :
la citation « RGAA 7/11 » pour les onglets a été remplacée par
**RGAA 7.1 + 7.3** (cf. §3, note de correction — la thématique 11 est
« Formulaires », sans rapport). Le nombre de labels (13, pas 16) et
d'indicateurs de focus (21, pas 20) ont aussi été recomptés directement
dans le fichier plutôt que repris d'une estimation précédente.

## 5. Comment reproduire cette vérification

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

## 6. Limites et écarts connus

1. **3 boutons "Actualiser"** (`templates/index.html`, vues client/analyste/exploitation) n'ont ni `focus:outline-none` ni `focus:ring` explicite — contrairement au reste de l'interface. Ce n'est **pas** un défaut fonctionnel : n'ayant pas retiré l'outline navigateur par défaut, ces boutons restent visibles au focus clavier (contour natif du navigateur) — c'est une **incohérence visuelle mineure** (style natif vs anneau bleu personnalisé ailleurs), pas une violation RGAA.
2. **Swagger UI** (`/apidocs`, bibliothèque tierce Flasgger) n'a pas été auditée indépendamment dans le cadre de ce projet — son accessibilité dépend entièrement du composant amont, hors du code de Waterflow.
3. Cette matrice couvre les fonctionnalités **vérifiées au cours des échanges de cette session** (formulaires, onglets, tableaux, alertes) — pas un audit RGAA complet et exhaustif (106 critères du référentiel officiel), qui nécessiterait un outil dédié et une revue méthodique critère par critère.
4. Un écart réel a été trouvé puis corrigé : le formulaire d'analyse manuelle contredisait l'acceptation critère de US-01 (labels non associés, pas d'`aria-live`) — corrigé, testé dans un vrai navigateur (voir §3, ligne en gras).

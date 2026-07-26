# Waterflow — Preuve C8 : paramétrage réel du service OCR

> Document de preuve : appuie le point du rapport E2 (§4.4, C8) *« Le service
> est configuré correctement, il répond aux besoins fonctionnels et aux
> contraintes techniques du projet »* avec des preuves **vérifiables**
> (correspondance configuration ↔ besoin, exécution réelle contre les vraies
> API OCR.space/Anthropic) plutôt que déclaratives. Un écart réel a été
> trouvé et corrigé au cours de cette vérification (§3) — la preuve inclut
> le cycle complet test → bug → correction → re-test, pas seulement un
> résultat final présenté comme acquis d'emblée.

## 1. Correspondance besoins fonctionnels (§3.1 du rapport E2) ↔ configuration réelle

| Besoin exprimé | Paramètre de configuration réel | Preuve dans le code |
|---|---|---|
| Extraction en français | `"language": "fre"` | `api/services/ocr_service.py::_ocr_space()` |
| Fiches labo = tableaux structurés | `"isTable": True`, `"OCREngine": 2` (moteur spécialisé tableaux) | idem |
| Virgule décimale → point | `float(str(val).replace(",", "."))` | `_normalise()` |
| Formats PDF/image acceptés | `ACCEPTED_MIME` (6 types MIME), PDF traité en bloc `document` natif chez Claude (pas de conversion image) | `_claude_vision_extract()` |
| Disponibilité malgré panne fournisseur | Cascade à 4 niveaux (nominal / dégradé / secours / indisponible), fallback automatique et transparent | `extract_from_document()` |
| Budget quasi nul | Plans gratuits exploités (OCR.space 25 000 req/mois) | `.env.example`, `docs/outils_test.md` |

## 2. Preuve d'exécution réelle — cycle test → bug → correction → re-test

Plutôt qu'une simple relecture de code, le service a été appelé **en
conditions réelles** (vraies clés `OCR_SPACE_API_KEY`/`ANTHROPIC_API_KEY`,
vrai fichier `samples/fiche_non_potable_test.pdf`) :

```python
from api.services.ocr_service import extract_from_document
with open("samples/fiche_non_potable_test.pdf", "rb") as f:
    file_bytes = f.read()
result = extract_from_document(file_bytes, "application/pdf")
```

### 2.1 Premier appel — un vrai bug trouvé

```
OCR.space échoué (Expecting ',' delimiter: line 15 column 4 (char 384)) — fallback Claude Vision
Appel réussi en 42.60s
mesures extraites : {'ph': 5.0, 'Hardness': 320.0, 'Solids': 55000.0, ...}
```

Le service a **répondu correctement au final** (bascule automatique vers le
niveau de secours, résultat exploitable) — mais le niveau 1 de la cascade
(OCR.space + structuration Claude) échouait silencieusement, masqué par le
fallback. Cause identifiée : `_claude_structure()` utilisait
`re.search(r"\{.*\}", clean, re.DOTALL)` — une regex gourmande qui capture
du premier `{` au tout dernier `}` du texte, fragile dès que la réponse
contient plusieurs blocs braced.

### 2.2 Correction n°1 — extraction JSON robuste

Nouvelle fonction `_extract_json()` (scan à accolades équilibrées, ignorant
celles internes aux chaînes), remplace la regex gourmande dans
`_claude_vision_extract()` **et** `_claude_structure()`.

Re-test avec cette seule correction — le message d'erreur devient
nettement plus précis, révélant la **vraie** cause racine :

```
OCR.space échoué (JSON incomplet (accolades non équilibrées) : {
  "date_prelevement": "2026-06-28", ...
  "Conductivity": 680.0) — fallback Claude Vision
Appel réussi en 41.22s
```

Le JSON était **tronqué en cours de génération**, pas mal formé — la
regex précédente masquait ce diagnostic derrière une erreur de parsing
générique.

### 2.3 Correction n°2 — cause racine

`_claude_structure()` utilisait `max_tokens=1024`, insuffisant car le JSON
de sortie doit inclure une transcription intégrale (`raw_text`) en plus des
mesures et avertissements — porté à `2048` (aligné sur
`_claude_vision_extract()`, qui n'avait pas ce problème).

### 2.4 Re-test final — succès sans bascule

```
Appel réussi en 18.09s
mesures extraites : {'ph': 5.0, 'Hardness': 320.0, 'Solids': 55000.0,
  'Chloramines': 12.5, 'Sulfate': 480.0, 'Conductivity': 680.0,
  'Organic_carbon': 28.0, 'Trihalomethanes': 120.0, 'Turbidity': 9.0}
```

Le niveau 1 de la cascade (OCR.space + structuration Claude) réussit
désormais **directement**, sans recours au niveau de secours — et
**2,3× plus rapide** (18s contre 42s), l'appel supplémentaire à Claude
Vision devenant inutile.

## 3. Ce que ce cycle démontre

- Le service n'est pas seulement configuré selon la documentation
  fournisseur : sa configuration **répond réellement** aux besoins
  fonctionnels du projet, vérifié par exécution et non par lecture seule.
- La marge d'erreur a été trouvée à l'endroit où elle se manifeste
  réellement (une réponse LLM tronquée en production), pas dans un
  scénario de test artificiel.
- La preuve inclut l'échec initial, pas seulement le succès final — la
  configuration a été **améliorée** au cours de cette vérification, ce qui
  est une preuve plus forte qu'une affirmation de conformité a priori.

## 4. Reproduire cette vérification

```bash
python -c "
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
from dotenv import load_dotenv; load_dotenv()
from api.services.ocr_service import extract_from_document
with open('samples/fiche_non_potable_test.pdf', 'rb') as f:
    result = extract_from_document(f.read(), 'application/pdf')
print(result['mesures'])
"
```

Nécessite `OCR_SPACE_API_KEY` et `ANTHROPIC_API_KEY` valides dans `.env`.

## 5. Limites

- Ce test a été exécuté sur un seul document réel (`fiche_non_potable_test.pdf`) ;
  il ne constitue pas une campagne de test systématique sur un corpus
  représentatif de fiches labo variées (qualité de scan, écriture
  manuscrite, mises en page différentes).
- Le correctif porte sur la robustesse de l'extraction JSON et sur une
  limite de tokens insuffisante ; il ne garantit pas l'absence d'autres
  troncatures possibles sur des documents encore plus volumineux — une
  limite haute de `max_tokens` reste fixe (2048), pas adaptative à la
  taille du document source.

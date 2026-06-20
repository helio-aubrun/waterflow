# Waterflow 2 — Plateforme MLOps Qualité Eau
## Architecture

```
waterflow2/
├── api/
│   ├── app.py                  # Factory Flask
│   ├── models/db.py            # SQLAlchemy (RGPD)
│   ├── middleware/auth.py      # Auth clé API multi-profil + audit
│   ├── routes/routes.py        # Toutes les routes
│   └── services/
│       ├── ocr_service.py      # OCR.space + fallback Claude Vision
│       └── predict_service.py  # XGBoost via MLflow
├── frontend/templates/index.html  # Interface web
├── tests/test_api.py           # Tests automatisés
├── main.py                     # Point d'entrée
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .github/workflows/ci.yml    # CI/CD GitHub Actions
```

## Démarrage rapide

```bash
# 1. Variables d'environnement
cp .env.example .env
# Renseigner OCR_SPACE_API_KEY et/ou ANTHROPIC_API_KEY

# 2. Lancement Docker
docker compose up -d

# 3. Créer un premier client admin via la DB ou un script d'init
python scripts/init_admin.py
```

## Routes API

| Méthode | Route                         | Profil requis      | Description                        |
|---------|-------------------------------|--------------------|------------------------------------|
| GET     | /health                       | public             | État du service                    |
| POST    | /predict                      | terrain+           | Prédiction JSON                    |
| POST    | /ocr                          | terrain+           | Extraction OCR fiche               |
| POST    | /ocr-and-predict              | terrain+           | OCR + prédiction pipeline complet  |
| GET     | /data/prelevements            | analyste, admin    | Liste paginée                      |
| GET     | /data/prelevements/<id>       | analyste, admin    | Détail prélèvement                 |
| GET     | /data/dashboard               | analyste, admin    | KPIs agrégés                       |
| POST    | /admin/clients                | admin              | Créer client                       |
| GET     | /admin/clients                | admin              | Lister clients                     |
| POST    | /admin/clients/<id>/apikey    | admin              | Générer clé API                    |
| GET     | /metrics                      | admin              | Métriques monitoring               |

## Tests

```bash
pytest tests/ -v --cov=api
```

## Variables d'environnement

| Variable            | Obligatoire | Défaut                              |
|---------------------|-------------|-------------------------------------|
| DATABASE_URL        | non         | sqlite:///waterflow2.db             |
| MLFLOW_URI          | non         | models:/WaterQualityXGBoost/1       |
| SCALER_PATH         | non         | model_artifacts/robust_scaler.pkl   |
| OCR_SPACE_API_KEY   | non*        | ""                                  |
| ANTHROPIC_API_KEY   | non*        | ""                                  |
| MAX_UPLOAD_MB       | non         | 20                                  |

*Au moins l'une des deux clés OCR est requise pour /ocr et /ocr-and-predict.

## Conformité RGPD

- Emails stockés en SHA-256 uniquement
- IPs pseudonymisées dans les logs (masquage du dernier octet)
- Clés API stockées hashées (SHA-256), jamais en clair
- Table `audit_logs` immuable pour traçabilité
- Champ `anonymised_at` sur Client pour droit à l'effacement
- Consentement RGPD explicite tracé (`rgpd_consent`, `rgpd_consent_at`)

# 🤖 Machine Learning Operations (MLOps)

## Définition

Le **MLOps** (Machine Learning Operations) est un ensemble de pratiques, d'outils et de processus visant à **standardiser et automatiser le cycle de vie des modèles de Machine Learning** en production — de leur développement jusqu'à leur déploiement et leur maintenance.

Il s'inspire du DevOps appliqué au développement logiciel, en l'adaptant aux spécificités des systèmes d'IA : données évolutives, modèles à réentraîner, et résultats probabilistes.

---

## Pourquoi le MLOps ?

Sans MLOps, les équipes Data Science font face à des défis récurrents :

- Des modèles performants en expérimentation qui **échouent en production**
- Un manque de **reproductibilité** des expériences
- Une **dégradation silencieuse** des performances au fil du temps (data drift)
- Des pipelines manuels, lents et sources d'erreurs

Le MLOps répond à ces problèmes en apportant rigueur, automatisation et collaboration entre Data Scientists, ingénieurs ML et équipes Ops.

---

## Les grands piliers du MLOps

### 1. 📦 Gestion des données
- Versioning des datasets (ex : DVC, Delta Lake)
- Traçabilité et qualité des données
- Pipelines d'ingestion automatisés

### 2. 🧪 Expérimentation & versioning des modèles
- Suivi des expériences (ex : MLflow, Weights & Biases)
- Versioning des modèles et des hyperparamètres
- Reproductibilité garantie

### 3. 🔄 Pipelines CI/CD pour le ML
- Intégration continue : tests automatiques sur les données et le code
- Déploiement continu : mise en production automatisée
- Entraînement continu (CT) : réentraînement déclenché par des événements

### 4. 🚀 Déploiement & serving
- Conteneurisation des modèles (Docker, Kubernetes)
- API de prédiction (REST, gRPC)
- Stratégies de déploiement : canary, blue/green, A/B testing

### 5. 📊 Monitoring & observabilité
- Surveillance des performances en production
- Détection du **data drift** et du **concept drift**
- Alertes et tableaux de bord (ex : Evidently, Grafana)

### 6. 🔁 Feedback loop & réentraînement
- Collecte des nouvelles données issues de la production
- Réentraînement automatique ou semi-automatique
- Gouvernance et validation avant redéploiement

---

## Niveaux de maturité MLOps

| Niveau | Description |
|--------|-------------|
| **0** | Processus entièrement manuels, expérimentations ad hoc |
| **1** | Pipelines ML automatisés, entraînement continu |
| **2** | CI/CD complet, déploiement et monitoring automatisés |

---

## Outils courants

| Catégorie | Outils |
|-----------|--------|
| Expérimentation | MLflow, Weights & Biases, Neptune |
| Versioning données | DVC, LakeFS |
| Orchestration | Airflow, Kubeflow, Prefect |
| Serving | BentoML, Seldon, TorchServe, FastAPI |
| Monitoring | Evidently, Arize, WhyLabs |
| Plateforme complète | Azure ML, Google Vertex AI, AWS SageMaker |

---

## En résumé

> Le MLOps, c'est faire en sorte que les modèles de Machine Learning **fonctionnent de façon fiable, reproductible et évolutive** en production — pas seulement en notebook.

---

# 🧪 MLflow — Veille Technologique

> Plateforme open source de gestion du cycle de vie de l'apprentissage automatique  
> **Version installée : 3.12.0** · Mai 2026

---

## 📌 Table des matières

1. [Présentation](#présentation)
2. [Architecture — Les 4 composants](#architecture--les-4-composants)
3. [MLflow 3 — La révolution 2025](#mlflow-3--la-révolution-2025)
4. [Étendue de l'utilisation](#étendue-de-lutilisation)
5. [Intégrations](#intégrations)
6. [Installation](#installation)
7. [Démarrage rapide](#démarrage-rapide)
8. [Recommandations](#recommandations)

---

## Présentation

MLflow est la **plus grande plateforme open source d'ingénierie IA** pour les agents, les LLMs et les modèles de Machine Learning. Initialement développé par **Databricks**, il est aujourd'hui maintenu par une communauté de plus de **850 contributeurs** à travers le monde.

| Statistique | Valeur |
|---|---|
| 📥 Téléchargements mensuels | > 30 millions |
| 👥 Contributeurs | > 850 |
| 🏢 Organisations utilisatrices | Milliers d'entreprises |
| 📅 Dernière version | 3.12.0 (mai 2026) |
| 📜 Licence | Apache 2.0 (open source) |

**Philosophie :** MLflow repose sur un principe simple mais puissant — *log everything*. Chaque paramètre, métrique et artefact est enregistré automatiquement, rendant chaque expérience traçable, reproductible et comparable.

---

## Architecture — Les 4 composants

### 🔬 1. MLflow Tracking
Suivi des expériences ML en temps réel.

- Enregistrement des **hyperparamètres** (learning rate, batch size, etc.)
- Suivi des **métriques** (accuracy, loss, F1-score) en séries temporelles
- Stockage des **artefacts** (modèles, graphiques, fichiers)
- Interface web de **comparaison visuelle** des runs
- Backend local (`mlruns/`) ou serveur distant via REST API

```python
import mlflow

with mlflow.start_run():
    mlflow.log_param("n_estimators", 100)
    mlflow.log_metric("accuracy", 0.94)
    mlflow.sklearn.log_model(model, "model")
```

---

### 📦 2. MLflow Projects
Packaging reproductible des workflows ML.

- Format standardisé via un fichier `MLproject`
- Gestion des environnements (Conda, Docker, virtualenv)
- Exécution reproductible sur n'importe quelle machine
- Intégration native avec **Airflow**, **Kubernetes**

```yaml
# MLproject
name: water_potability
conda_env: conda.yaml
entry_points:
  train:
    parameters:
      n_estimators: {type: int, default: 100}
    command: "python train.py --n_estimators {n_estimators}"
```

---

### 🤖 3. MLflow Models
Format universel de packaging des modèles.

- Format `MLmodel` agnostique du framework
- Déploiement vers **REST API**, cloud, edge devices
- Serveur d'inférence intégré en une commande
- Support de **20+ frameworks** (sklearn, PyTorch, TensorFlow, HuggingFace…)

```bash
# Servir un modèle localement
mlflow models serve -m "models:/water_quality_model/Production" -p 1234

# Inférence via curl
curl -X POST http://localhost:1234/invocations \
  -H "Content-Type: application/json" \
  -d '{"dataframe_records": [{"ph": 7.2, "Hardness": 204.8}]}'
```

---

### 🗂️ 4. Model Registry
Versioning et gouvernance des modèles.

- **Versioning** centralisé de tous les modèles
- Gestion des stages : `None → Staging → Production → Archived`
- **Lineage** complet : lien entre modèle, runs, données et métriques
- Webhooks pour automatiser les pipelines CI/CD
- Contrôle d'accès et audit trail complet

```python
from mlflow import MlflowClient

client = MlflowClient()

# Enregistrer un modèle
mlflow.register_model("runs:/abc123/model", "WaterQualityClassifier")

# Promouvoir en Production
client.transition_model_version_stage(
    name="WaterQualityClassifier",
    version=2,
    stage="Production"
)
```

---

## MLflow 3 — La révolution 2025

Lancé en **juin 2025**, MLflow 3 marque un tournant majeur avec l'intégration native de l'IA générative.

### Nouveautés clés

| Fonctionnalité | Description |
|---|---|
| **LoggedModel** | Nouvelle entité première classe, au-delà des runs traditionnels |
| **GenAI Evaluation** | Évaluation systématique des LLMs et agents RAG |
| **Prompt Registry** | Versioning et optimisation automatique des prompts |
| **Tracing** | Observabilité complète des applications GenAI (OpenTelemetry) |
| **AI Gateway** | Gestion centralisée des coûts et accès aux modèles |
| **MCP Server** | Intégration avec Claude Code et autres assistants IA |
| **Multi-workspace** | Isolation logique dans un serveur unique |
| **Cost Tracking** | Suivi automatique des coûts LLM par trace |

### Chronologie des versions 2025–2026

```
MLflow 3.0   — Juin 2025      → GenAI & LoggedModel
MLflow 3.2   — Août 2025      → TypeScript SDK, Semantic Kernel
MLflow 3.4   → Helm chart K8s
MLflow 3.5   — Oct. 2025      → Job Execution Backend, Prompt Optimization
MLflow 3.7   — Déc. 2025      → Multi-turn Evaluation, Trace Comparison
MLflow 3.9   — Fév. 2026      → MLflow Assistant (Claude Code), Dashboards
MLflow 3.10  — Mars 2026      → Multi-workspace, Cost Tracking
MLflow 3.12  — Mai 2026       → Version actuelle ✅
```

---

## Étendue de l'utilisation

### 🔵 Machine Learning classique
- Expériences scikit-learn, XGBoost, LightGBM
- Tuning d'hyperparamètres (GridSearch, Optuna, Ray Tune)
- Évaluation et comparaison de modèles
- Déploiement REST ou batch

### 🟣 Deep Learning
- Suivi d'entraînement PyTorch / TensorFlow / Keras
- Gestion des checkpoints
- Visualisation des courbes de loss/accuracy

### 🟠 IA Générative & LLMs
- Tracing des pipelines RAG
- Évaluation de la qualité des réponses (hallucination, fidélité, pertinence)
- Gestion et optimisation des prompts
- Agents IA multi-étapes (LangChain, LlamaIndex, smolagents)

### 🏭 MLOps en production
- Pipelines CI/CD avec webhooks
- Gouvernance et audit trail des modèles
- Monitoring continu des performances
- Déploiement Kubernetes via Helm chart

---

## Intégrations

### Frameworks ML
`scikit-learn` · `XGBoost` · `LightGBM` · `PyTorch` · `TensorFlow` · `Keras` · `HuggingFace` · `Spark MLlib`

### Frameworks GenAI
`OpenAI` · `Anthropic` · `LangChain` · `LlamaIndex` · `smolagents` · `PydanticAI` · `Semantic Kernel` · `Agno`

### Infrastructure & Orchestration
`Databricks` · `Airflow` · `Kubernetes` · `Docker` · `AWS SageMaker` · `Azure ML` · `GCP Vertex AI`

### Stockage
`S3` · `GCS` · `Azure Blob` · `HDFS` · `NFS` · `PostgreSQL` · `MySQL` · `SQLite`

### Monitoring & Observabilité
`OpenTelemetry` · `DeepEval` · `RAGAS` · `Prometheus`

---

## Installation

### Installation standard

```bash
pip install mlflow
```

### Vérification

```bash
python -c "import mlflow; print(mlflow.__version__)"
# → 3.12.0
```

### Avec dépendances du projet

Ajouter au `requirements.txt` :

```
mlflow==3.12.0
```

### Lancer l'interface web

```bash
mlflow ui
# → http://localhost:5000
```

### Lancer un serveur de tracking distant

```bash
mlflow server \
  --backend-store-uri postgresql://user:pwd@localhost/mlflow \
  --default-artifact-root s3://my-bucket/mlflow \
  --host 0.0.0.0 \
  --port 5000
```

---

## Démarrage rapide

Exemple appliqué au projet **water_potability** :

```python
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

# Configurer l'expérience
mlflow.set_experiment("water_potability_classification")

# Activer l'autologging
mlflow.sklearn.autolog()

with mlflow.start_run(run_name="RandomForest_v1"):

    # Paramètres
    params = {"n_estimators": 200, "max_depth": 10, "class_weight": "balanced"}
    model = RandomForestClassifier(**params, random_state=42)
    model.fit(X_train, y_train)

    # Métriques manuelles
    preds = model.predict(X_test)
    mlflow.log_metric("f1_score",  f1_score(y_test, preds))
    mlflow.log_metric("roc_auc",   roc_auc_score(y_test, preds))

    # Tags
    mlflow.set_tag("dataset", "water_potability_clean.csv")
    mlflow.set_tag("preprocessing", "winsorization + median imputation")

    # Enregistrer le modèle
    mlflow.sklearn.log_model(model, "model",
                             registered_model_name="WaterQualityClassifier")
```

---

## Recommandations

### ✅ Points forts
- **Open source & vendor-neutral** — aucun lock-in propriétaire
- **Agnostique des frameworks** — fonctionne avec tout l'écosystème ML/GenAI
- **Déploiement flexible** — local, on-premise, cloud
- **Communauté massive** — 30M+ downloads/mois, support actif
- **MLflow 3** — unifie ML classique et GenAI dans une seule plateforme

### ⚠️ Points de vigilance
- L'interface UI peut être lente avec de nombreux runs
- La sécurité en mode self-hosted est à configurer manuellement
- La courbe d'apprentissage pour les fonctionnalités avancées (GenAI, tracing) est modérée

### 🔗 Ressources utiles

| Ressource | Lien |
|---|---|
| Documentation officielle | https://mlflow.org/docs/latest/ |
| GitHub | https://github.com/mlflow/mlflow |
| Releases | https://mlflow.org/releases/ |
| Tutoriels | https://mlflow.org/docs/latest/getting-started/ |

---
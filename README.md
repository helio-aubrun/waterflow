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

*Veille réalisée dans le cadre d'une étude sur les pratiques modernes du Machine Learning en entreprise.*
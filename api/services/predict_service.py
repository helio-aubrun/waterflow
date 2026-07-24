"""
api/services/predict_service.py — Service de prédiction XGBoost

Chargement unique du modèle au démarrage.
Expose run_prediction() utilisé par toutes les routes.

Le modèle et le scaler sont chargés DIRECTEMENT depuis model_artifacts/
(xgboost_model.json, robust_scaler.pkl) plutôt que via le registre MLflow
Model Registry (mlflow.xgboost.load_model("models:/...")). Le registre
MLflow dépend d'un état local (mlflow_water.db) dont le schéma doit
correspondre exactement à la version de mlflow installée — un
désalignement (mlflow mis à jour sans migrer la base, registre jamais
peuplé sur une nouvelle machine, etc.) casse toute prédiction avec une
erreur qui n'a rien à voir avec le modèle lui-même. Les fichiers modèle
et scaler, eux, sont versionnés dans le dépôt et ne dépendent d'aucun
état local — ce chemin fonctionne à l'identique sur n'importe quelle
machine, sans dépendre d'un tracking MLflow préalablement configuré.
"""

import os
import logging

import joblib
import numpy as np
import xgboost

logger = logging.getLogger(__name__)

MODEL_PATH   = os.getenv("MODEL_PATH",  "model_artifacts/xgboost_model.json")
SCALER_PATH  = os.getenv("SCALER_PATH", "model_artifacts/robust_scaler.pkl")
MODEL_VERSION = os.path.basename(MODEL_PATH)

FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity",
]

_model  = None
_scaler = None


def _ensure_loaded() -> None:
    global _model, _scaler
    if _model is not None:
        return
    logger.info("Chargement modèle XGBoost : %s", MODEL_PATH)
    _model = xgboost.XGBClassifier()
    _model.load_model(MODEL_PATH)
    logger.info("Chargement scaler : %s", SCALER_PATH)
    _scaler = joblib.load(SCALER_PATH)
    logger.info("Modèle prêt.")


def run_prediction(mesures: dict) -> dict:
    _ensure_loaded()
    missing = [f for f in FEATURES if mesures.get(f) is None]
    if missing:
        raise ValueError(f"Features manquantes ou nulles : {missing}")

    try:
        values = np.array([[float(mesures[f]) for f in FEATURES]])
    except (TypeError, ValueError) as e:
        raise ValueError(f"Valeur non numérique dans les mesures : {e}") from e

    values_scaled = _scaler.transform(values)
    prediction    = int(_model.predict(values_scaled)[0])
    probability   = float(_model.predict_proba(values_scaled)[0][1])

    return {
        "potable":     prediction,
        "label":       "Potable" if prediction == 1 else "Non potable",
        "probability": round(probability, 4),
        "model_version": MODEL_VERSION,
    }

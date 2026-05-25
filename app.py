"""
Flask API — Potabilité de l'Eau
Prérequis : avoir exécuté water_xgboost.ipynb et water_mlflow_server.ipynb
"""

import joblib
import numpy as np
import mlflow.xgboost
from flask import Flask, request, jsonify

app = Flask(__name__)

# Chargement au démarrage — une seule fois
MLFLOW_MODEL_URI = "models:/WaterQualityXGBoost/1"
SCALER_PATH      = "model_artifacts/robust_scaler.pkl"
FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"
]

mlflow.set_tracking_uri("sqlite:///mlflow_water.db")
model  = mlflow.xgboost.load_model(MLFLOW_MODEL_URI)
scaler = joblib.load(SCALER_PATH)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MLFLOW_MODEL_URI})


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(force=True)

    # Validation : les 9 features doivent être présentes
    missing = [f for f in FEATURES if f not in data]
    if missing:
        return jsonify({"error": f"Features manquantes : {missing}"}), 400

    try:
        values = np.array([[float(data[f]) for f in FEATURES]])
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Valeur non numérique : {e}"}), 400

    # Scaling + prédiction
    values_scaled = scaler.transform(values)
    prediction    = int(model.predict(values_scaled)[0])
    probability   = float(model.predict_proba(values_scaled)[0][1])

    return jsonify({
        "potable":     prediction,
        "label":       "Potable" if prediction == 1 else "Non potable",
        "probability": round(probability, 4),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

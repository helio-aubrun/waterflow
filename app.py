"""
Flask API — Potabilité de l'Eau
Sécurisée par clé API (header X-API-Key ou param ?api_key=...)

Prérequis : avoir exécuté water_xgboost.ipynb et water_mlflow_server.ipynb

Variables d'environnement :
  API_KEYS   — liste de clés séparées par des virgules (obligatoire)
               ex: API_KEYS="cle-commune-A,cle-commune-B"
  MLFLOW_URI — URI du modèle MLflow (défaut : models:/WaterQualityXGBoost/1)
  SCALER_PATH— chemin du scaler (défaut : model_artifacts/robust_scaler.pkl)
"""

import os
import time
import hashlib
import logging
from functools import wraps

import joblib
import numpy as np
import mlflow.xgboost
from flask import Flask, request, jsonify, render_template, g

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MLFLOW_MODEL_URI = os.getenv("MLFLOW_URI", "models:/WaterQualityXGBoost/1")
SCALER_PATH      = os.getenv("SCALER_PATH", "model_artifacts/robust_scaler.pkl")

FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity",
]

# ---------------------------------------------------------------------------
# Gestion des clés API
# ---------------------------------------------------------------------------

def _load_api_keys() -> set[str]:
    """
    Lit les clés depuis la variable d'environnement API_KEYS.
    Chaque clé est stockée sous forme de hash SHA-256 pour éviter
    de garder les secrets en clair en mémoire.
    """
    raw = os.getenv("API_KEYS", "")
    keys = {k.strip() for k in raw.split(",") if k.strip()}
    if not keys:
        raise RuntimeError(
            "Aucune clé API définie. "
            "Renseignez la variable d'environnement API_KEYS."
        )
    # Stockage sous forme de hash : comparaison en temps constant via hmac
    return {hashlib.sha256(k.encode()).hexdigest() for k in keys}

HASHED_KEYS: set[str] = _load_api_keys()


def _check_api_key(key: str | None) -> bool:
    """Vérifie une clé fournie contre les hashs enregistrés."""
    if not key:
        return False
    candidate = hashlib.sha256(key.encode()).hexdigest()
    # comparaison en temps constant pour limiter les timing attacks
    return any(
        hashlib.compare_digest(candidate, stored)
        for stored in HASHED_KEYS
    )


def require_api_key(f):
    """
    Décorateur — refuse les requêtes sans clé valide.
    La clé peut être transmise :
      • dans le header   X-API-Key: <clé>
      • dans le paramètre URL  ?api_key=<clé>
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        key = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
        )
        if not _check_api_key(key):
            logger.warning(
                "Accès refusé — clé invalide ou absente | IP=%s path=%s",
                request.remote_addr,
                request.path,
            )
            return jsonify({"error": "Clé API invalide ou absente."}), 401
        # On masque la clé dans les logs en ne gardant que les 4 premiers chars
        g.api_key_hint = (key or "")[:4] + "…"
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Chargement du modèle (une seule fois au démarrage)
# ---------------------------------------------------------------------------

mlflow.set_tracking_uri("sqlite:///mlflow_water.db")

logger.info("Chargement du modèle MLflow : %s", MLFLOW_MODEL_URI)
model = mlflow.xgboost.load_model(MLFLOW_MODEL_URI)

logger.info("Chargement du scaler : %s", SCALER_PATH)
scaler = joblib.load(SCALER_PATH)

logger.info("Modèle et scaler prêts.")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    """Point de contrôle public — pas de clé requise."""
    return jsonify({"status": "ok", "model": MLFLOW_MODEL_URI})


@app.route("/predict", methods=["POST"])
@require_api_key
def predict():
    """
    Prédit la potabilité d'un échantillon d'eau.

    Corps JSON attendu :
    {
        "ph": 7.2,
        "Hardness": 198.0,
        "Solids": 18630.0,
        "Chloramines": 7.1,
        "Sulfate": 333.0,
        "Conductivity": 432.0,
        "Organic_carbon": 14.2,
        "Trihalomethanes": 62.8,
        "Turbidity": 4.0
    }

    Réponse :
    {
        "potable": 1,
        "label": "Potable",
        "probability": 0.8312
    }
    """
    t0 = time.perf_counter()

    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Le corps de la requête doit être un objet JSON."}), 400

    # Validation des features
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

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "Prédiction OK | clé=%s label=%s proba=%.4f durée=%sms",
        g.get("api_key_hint", "?"),
        "Potable" if prediction == 1 else "Non potable",
        probability,
        elapsed_ms,
    )

    return jsonify({
        "potable":     prediction,
        "label":       "Potable" if prediction == 1 else "Non potable",
        "probability": round(probability, 4),
    })


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)

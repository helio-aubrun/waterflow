"""
tests/test_model_validation.py — CI du modèle ML

Ces tests chargent les vrais artefacts (modèle, scaler, données de validation).
Ils ne mockent rien : ils vérifient que le modèle en production est correct.

Quatre axes :
  1. Intégrité des artefacts  — les fichiers existent et sont chargeable
  2. Performance minimale     — les métriques respectent les seuils fixés
  3. Comportement d'inférence — le modèle produit des sorties cohérentes
  4. Stabilité                — cohérence entre prédictions actuelles et sauvegardées
"""

import os
import json
import pytest
import numpy as np
import pandas as pd
import joblib
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    average_precision_score, precision_score, recall_score,
)

# ── Chemins artefacts ────────────────────────────────────────────────────────

ROOT          = os.path.dirname(os.path.dirname(__file__))
ARTIFACTS_DIR = os.path.join(ROOT, "model_artifacts")

MODEL_PATH    = os.path.join(ARTIFACTS_DIR, "xgboost_model.json")
SCALER_PATH   = os.path.join(ARTIFACTS_DIR, "robust_scaler.pkl")
METADATA_PATH = os.path.join(ARTIFACTS_DIR, "metadata.json")
X_VAL_PATH    = os.path.join(ARTIFACTS_DIR, "X_val_sc.npy")
Y_VAL_PATH    = os.path.join(ARTIFACTS_DIR, "y_val.npy")
Y_PRED_PATH   = os.path.join(ARTIFACTS_DIR, "y_pred.npy")
Y_PROB_PATH   = os.path.join(ARTIFACTS_DIR, "y_pred_prob.npy")
CV_PATH       = os.path.join(ARTIFACTS_DIR, "cv_scores.npy")

FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity",
]

# ── Seuils de performance minimaux ──────────────────────────────────────────
# Définis à partir des métriques de référence du dernier entraînement validé.
# Le CI échoue si le modèle rechargé passe en dessous de ces seuils.

THRESHOLDS = {
    "accuracy":   0.60,
    "f1":         0.45,
    "roc_auc":    0.60,
    "pr_auc":     0.55,
    "cv_mean":    0.62,
    "cv_std_max": 0.05,   # instabilité CV inacceptable au-delà
}

# Tolérance pour la comparaison prédictions actuelles vs sauvegardées
PRED_TOLERANCE = 1e-4


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def metadata():
    with open(METADATA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def model():
    m = xgb.XGBClassifier()
    m.load_model(MODEL_PATH)
    return m


@pytest.fixture(scope="module")
def scaler():
    return joblib.load(SCALER_PATH)


@pytest.fixture(scope="module")
def val_data():
    return {
        "X": np.load(X_VAL_PATH),
        "y": np.load(Y_VAL_PATH),
    }


@pytest.fixture(scope="module")
def saved_predictions():
    return {
        "y_pred": np.load(Y_PRED_PATH),
        "y_prob": np.load(Y_PROB_PATH),
    }


@pytest.fixture(scope="module")
def cv_scores():
    return np.load(CV_PATH)


@pytest.fixture(scope="module")
def live_predictions(model, val_data):
    """Prédictions recalculées en live sur le jeu de validation."""
    y_pred = model.predict(val_data["X"])
    y_prob = model.predict_proba(val_data["X"])[:, 1]
    return {"y_pred": y_pred, "y_prob": y_prob}


# ════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Intégrité des artefacts
# ════════════════════════════════════════════════════════════════════════════

class TestArtefacts:
    """Vérifie que tous les fichiers nécessaires existent et sont valides."""

    def test_modele_existe(self):
        assert os.path.exists(MODEL_PATH), f"Modèle introuvable : {MODEL_PATH}"

    def test_scaler_existe(self):
        assert os.path.exists(SCALER_PATH), f"Scaler introuvable : {SCALER_PATH}"

    def test_metadata_existe(self):
        assert os.path.exists(METADATA_PATH), f"Métadonnées introuvables : {METADATA_PATH}"

    def test_donnees_validation_existent(self):
        for path in [X_VAL_PATH, Y_VAL_PATH, Y_PRED_PATH, Y_PROB_PATH, CV_PATH]:
            assert os.path.exists(path), f"Fichier manquant : {path}"

    def test_modele_chargeable(self, model):
        """Le modèle doit se charger sans erreur."""
        assert model is not None
        assert hasattr(model, "predict")
        assert hasattr(model, "predict_proba")

    def test_scaler_chargeable(self, scaler):
        assert scaler is not None
        assert hasattr(scaler, "transform")

    def test_metadata_contient_champs_requis(self, metadata):
        for champ in ["features", "params", "metrics", "cv_mean", "cv_std", "n_val"]:
            assert champ in metadata, f"Champ manquant dans metadata.json : {champ}"

    def test_metadata_features_correctes(self, metadata):
        assert metadata["features"] == FEATURES

    def test_donnees_val_shape_coherente(self, val_data):
        X, y = val_data["X"], val_data["y"]
        assert X.ndim == 2, "X_val doit être 2D"
        assert X.shape[1] == 9, f"Attendu 9 features, obtenu {X.shape[1]}"
        assert X.shape[0] == y.shape[0], "X et y doivent avoir le même nombre de lignes"
        assert X.shape[0] == int(metadata["n_val"]) if (metadata := json.load(open(METADATA_PATH))) else True

    def test_cible_binaire(self, val_data):
        assert set(np.unique(val_data["y"])).issubset({0, 1})


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Performance minimale
# ════════════════════════════════════════════════════════════════════════════

class TestPerformance:
    """
    Recharge le modèle et calcule les métriques en live.
    Échoue si une métrique passe sous le seuil défini dans THRESHOLDS.
    """

    def test_accuracy_minimale(self, live_predictions, val_data):
        acc = accuracy_score(val_data["y"], live_predictions["y_pred"])
        assert acc >= THRESHOLDS["accuracy"], (
            f"Accuracy {acc:.4f} < seuil {THRESHOLDS['accuracy']}"
        )

    def test_f1_minimal(self, live_predictions, val_data):
        f1 = f1_score(val_data["y"], live_predictions["y_pred"])
        assert f1 >= THRESHOLDS["f1"], (
            f"F1 {f1:.4f} < seuil {THRESHOLDS['f1']}"
        )

    def test_roc_auc_minimal(self, live_predictions, val_data):
        auc = roc_auc_score(val_data["y"], live_predictions["y_prob"])
        assert auc >= THRESHOLDS["roc_auc"], (
            f"ROC-AUC {auc:.4f} < seuil {THRESHOLDS['roc_auc']}"
        )

    def test_pr_auc_minimal(self, live_predictions, val_data):
        pr_auc = average_precision_score(val_data["y"], live_predictions["y_prob"])
        assert pr_auc >= THRESHOLDS["pr_auc"], (
            f"PR-AUC {pr_auc:.4f} < seuil {THRESHOLDS['pr_auc']}"
        )

    def test_cv_mean_minimal(self, cv_scores):
        assert cv_scores.mean() >= THRESHOLDS["cv_mean"], (
            f"CV mean {cv_scores.mean():.4f} < seuil {THRESHOLDS['cv_mean']}"
        )

    def test_cv_stabilite(self, cv_scores):
        """Un écart-type CV élevé signale un modèle instable."""
        assert cv_scores.std() <= THRESHOLDS["cv_std_max"], (
            f"CV std {cv_scores.std():.4f} > seuil max {THRESHOLDS['cv_std_max']} — modèle instable"
        )

    def test_precision_rappel_equilibres(self, live_predictions, val_data):
        """Précision et rappel ne doivent pas être trop déséquilibrés (ratio < 2)."""
        prec = precision_score(val_data["y"], live_predictions["y_pred"])
        rec  = recall_score(val_data["y"], live_predictions["y_pred"])
        ratio = max(prec, rec) / (min(prec, rec) + 1e-9)
        assert ratio < 2.0, (
            f"Déséquilibre précision/rappel trop fort : {prec:.3f} / {rec:.3f} (ratio={ratio:.2f})"
        )

    def test_metriques_coherentes_avec_metadata(self, live_predictions, val_data, metadata):
        """Les métriques live doivent rester proches de celles sauvegardées (±5%)."""
        auc_live = roc_auc_score(val_data["y"], live_predictions["y_prob"])
        auc_ref  = metadata["metrics"]["ROC-AUC"]
        assert abs(auc_live - auc_ref) < 0.05, (
            f"ROC-AUC live {auc_live:.4f} diverge de la référence {auc_ref:.4f}"
        )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Comportement d'inférence
# ════════════════════════════════════════════════════════════════════════════

class TestInference:
    """Vérifie que le modèle se comporte correctement sur des inputs contrôlés."""

    # Encapsulés dans un DataFrame nommé (colonnes = FEATURES) pour éviter le
    # UserWarning sklearn "X does not have valid feature names" : le scaler a
    # été entraîné (fit) sur un DataFrame nommé, il doit recevoir la même
    # structure en inférence.
    SAMPLE_POTABLE = pd.DataFrame(
        [[7.0, 200.0, 20000.0, 7.5, 350.0, 400.0, 14.0, 66.0, 3.5]], columns=FEATURES
    )
    SAMPLE_DOUTEUX = pd.DataFrame(
        [[5.0, 320.0, 55000.0, 12.5, 480.0, 680.0, 28.0, 120.0, 9.0]], columns=FEATURES
    )

    def test_sortie_binaire(self, model, scaler):
        """La prédiction doit être 0 ou 1."""
        X = scaler.transform(self.SAMPLE_POTABLE)
        pred = model.predict(X)[0]
        assert pred in (0, 1), f"Prédiction inattendue : {pred}"

    def test_probabilite_dans_intervalle(self, model, scaler):
        """La probabilité doit être dans [0, 1]."""
        X = scaler.transform(self.SAMPLE_POTABLE)
        prob = model.predict_proba(X)[0][1]
        assert 0.0 <= prob <= 1.0, f"Probabilité hors intervalle : {prob}"

    def test_predict_proba_somme_a_1(self, model, scaler):
        """Les deux classes doivent sommer à 1."""
        X = scaler.transform(self.SAMPLE_POTABLE)
        proba = model.predict_proba(X)[0]
        assert abs(proba.sum() - 1.0) < 1e-6

    def test_sample_douteux_non_potable(self, model, scaler):
        """Un échantillon avec valeurs extrêmes (pH=5, solids=55000…) doit être classé non potable."""
        X = scaler.transform(self.SAMPLE_DOUTEUX)
        pred = model.predict(X)[0]
        assert pred == 0, f"Attendu Non potable (0), obtenu {pred}"

    def test_n_features_attendues(self, model):
        """Le modèle doit attendre exactement 9 features."""
        assert model.n_features_in_ == 9

    def test_scaler_preserve_shape(self, scaler):
        """Le scaler ne doit pas modifier la forme de l'array."""
        X = self.SAMPLE_POTABLE
        assert scaler.transform(X).shape == X.shape

    def test_batch_inference(self, model, scaler, val_data):
        """L'inférence batch doit produire autant de prédictions que de lignes."""
        preds = model.predict(val_data["X"])
        assert len(preds) == val_data["X"].shape[0]

    def test_inference_deterministe(self, model, scaler):
        """Le même input doit toujours produire le même output."""
        X = scaler.transform(self.SAMPLE_POTABLE)
        pred1 = model.predict(X)[0]
        pred2 = model.predict(X)[0]
        assert pred1 == pred2


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Stabilité (comparaison avec prédictions sauvegardées)
# ════════════════════════════════════════════════════════════════════════════

class TestStabilite:
    """
    Compare les prédictions recalculées en live avec celles sauvegardées
    lors de l'entraînement. Détecte une régression silencieuse du modèle.
    """

    def test_predictions_identiques_aux_sauvegardees(
        self, live_predictions, saved_predictions
    ):
        """Les classes prédites doivent être identiques à celles sauvegardées."""
        assert np.array_equal(
            live_predictions["y_pred"],
            saved_predictions["y_pred"]
        ), "Les prédictions live divergent des prédictions sauvegardées — modèle modifié ?"

    def test_probabilites_proches_des_sauvegardees(
        self, live_predictions, saved_predictions
    ):
        """Les probabilités live doivent être très proches des sauvegardées."""
        diff = np.abs(live_predictions["y_prob"] - saved_predictions["y_prob"])
        assert diff.max() < PRED_TOLERANCE, (
            f"Divergence max des probabilités : {diff.max():.2e} > tolérance {PRED_TOLERANCE}"
        )

    def test_taux_potabilite_stable(self, live_predictions, saved_predictions):
        """Le taux de potabilité prédit ne doit pas avoir changé."""
        rate_live  = live_predictions["y_pred"].mean()
        rate_saved = saved_predictions["y_pred"].mean()
        assert abs(rate_live - rate_saved) < 0.01, (
            f"Taux potabilité live={rate_live:.3f} vs sauvegardé={rate_saved:.3f}"
        )

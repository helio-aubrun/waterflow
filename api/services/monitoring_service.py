"""
api/services/monitoring_service.py — Monitoring du modèle ML

Trois axes :
  1. Data drift    — PSI par feature (Production vs baseline entraînement)
  2. Dégradation   — Distribution des probabilités + taux potabilité
  3. Alertes       — Seuils PSI, confiance, dérive du taux de potabilité

Note PSI : fiable uniquement à partir de MIN_SAMPLES_PSI échantillons.
En dessous, le niveau est "insufficient_data" (pas d'alerte critique).
Lissage de Laplace (alpha=1) pour éviter les PSI explosifs sur bins vides.
"""

import json
import math
import os
import logging
from datetime import datetime, timezone, timedelta

import numpy as np

logger = logging.getLogger(__name__)

TRAINING_STATS_PATH = os.getenv("TRAINING_STATS_PATH", "model_artifacts/training_stats.json")

# PSI (Population Stability Index)
PSI_OK   = 0.10   # vert  — stable
PSI_WARN = 0.20   # jaune — dérive modérée  /  > 0.20 → critique

# Nombre minimum d'échantillons pour que le PSI soit fiable
MIN_SAMPLES_PSI = 50

# Lissage de Laplace : évite les bins à 0 qui explosent le PSI
PSI_LAPLACE_ALPHA = 1.0

# Confiance moyenne minimale acceptable
CONFIDENCE_WARN = 0.65

# Écart absolu acceptable sur le taux de potabilité vs baseline
POTABILITY_DRIFT_WARN = 0.15

FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity",
]

_training_stats: dict | None = None


def _load_training_stats() -> dict:
    global _training_stats
    if _training_stats is None:
        with open(TRAINING_STATS_PATH, "r") as f:
            _training_stats = json.load(f)
    return _training_stats


def _psi(expected_pct: list[float], actual_pct: list[float]) -> float:
    """
    PSI avec lissage de Laplace sur actual_pct pour éviter log(0).
    Les expected_pct viennent du baseline et sont déjà non-nuls.
    """
    n_bins = len(expected_pct)
    total_actual = sum(actual_pct)

    # Lissage Laplace : (count + alpha) / (total + alpha * k)
    smoothed = [
        (a * total_actual + PSI_LAPLACE_ALPHA) / (total_actual + PSI_LAPLACE_ALPHA * n_bins)
        for a in actual_pct
    ]

    score = 0.0
    for e, a in zip(expected_pct, smoothed):
        e = max(e, 1e-9)
        score += (a - e) * math.log(a / e)
    return round(score, 6)


def _psi_level(psi: float, n_samples: int) -> str:
    if n_samples < MIN_SAMPLES_PSI:
        return "insufficient_data"
    if psi < PSI_OK:
        return "ok"
    if psi < PSI_WARN:
        return "warn"
    return "critical"


def _bin_values(values: list[float], bin_edges: list[float]) -> list[float]:
    """Répartit les valeurs dans les bins du baseline. Retourne les proportions brutes."""
    n_bins = len(bin_edges) - 1
    if not values:
        return [1.0 / n_bins] * n_bins
    counts = [0] * n_bins
    for v in values:
        placed = False
        for i in range(n_bins):
            if bin_edges[i] <= v < bin_edges[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    total = sum(counts)
    return [c / total for c in counts]


def compute_drift(db, window_days: int = 30) -> dict:
    """
    Calcule le drift PSI pour chaque feature sur la fenêtre glissante.
    level = 'insufficient_data' si moins de MIN_SAMPLES_PSI mesures.
    """
    from api.models.db import Mesure, Prelevement

    stats = _load_training_stats()
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)

    rows = (
        db.query(Mesure)
        .join(Prelevement, Mesure.prelevement_id == Prelevement.id)
        .filter(Prelevement.created_at >= since)
        .all()
    )

    results = {}
    for feat in FEATURES:
        col    = feat.lower()
        values = [getattr(r, col) for r in rows if getattr(r, col) is not None]
        ref    = stats["features"][feat]
        n      = len(values)

        actual_pct = _bin_values(values, ref["bin_edges"])
        psi        = _psi(ref["expected_pct"], actual_pct)
        level      = _psi_level(psi, n)

        prod_mean = round(float(np.mean(values)), 4) if values else None
        results[feat] = {
            "psi":        psi,
            "level":      level,
            "n_samples":  n,
            "prod_mean":  prod_mean,
            "train_mean": ref["mean"],
            "mean_delta": round(prod_mean - ref["mean"], 4) if prod_mean is not None else None,
        }

    return results


def compute_confidence_metrics(db, window_days: int = 30) -> dict:
    """Analyse la distribution des scores de confiance et du taux de potabilité."""
    from api.models.db import Prediction, Prelevement

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)

    preds = (
        db.query(Prediction)
        .join(Prelevement, Prediction.prelevement_id == Prelevement.id)
        .filter(Prelevement.created_at >= since)
        .all()
    )

    if not preds:
        return {"n_predictions": 0, "status": "no_data"}

    probs     = [p.probability for p in preds]
    avg_conf  = round(float(np.mean(probs)), 4)
    uncertain = sum(1 for p in probs if 0.4 <= p <= 0.6)
    potable   = sum(1 for p in preds if p.potable == 1)

    return {
        "n_predictions":    len(preds),
        "avg_confidence":   avg_conf,
        "pct_uncertain":    round(uncertain / len(preds), 4),
        "potability_rate":  round(potable / len(preds), 4),
        "confidence_level": "ok" if avg_conf >= CONFIDENCE_WARN else "warn",
    }


def compute_alerts(drift: dict, confidence: dict, training_stats: dict) -> list[dict]:
    """Génère les alertes actives. Ignore les features en 'insufficient_data'."""
    alerts = []
    now    = datetime.now(timezone.utc).isoformat()

    for feat, d in drift.items():
        if d["level"] == "critical":
            alerts.append({
                "type":      "data_drift",
                "severity":  "critical",
                "feature":   feat,
                "message":   f"Dérive critique sur {feat} (PSI={d['psi']:.3f} > {PSI_WARN})",
                "detail":    f"Moyenne prod={d['prod_mean']} vs train={d['train_mean']}",
                "timestamp": now,
            })
        elif d["level"] == "warn":
            alerts.append({
                "type":      "data_drift",
                "severity":  "warning",
                "feature":   feat,
                "message":   f"Dérive modérée sur {feat} (PSI={d['psi']:.3f})",
                "detail":    f"Moyenne prod={d['prod_mean']} vs train={d['train_mean']}",
                "timestamp": now,
            })

    if confidence.get("n_predictions", 0) > 0:
        if confidence["confidence_level"] == "warn":
            alerts.append({
                "type":      "low_confidence",
                "severity":  "warning",
                "feature":   None,
                "message":   f"Confiance moyenne faible ({confidence['avg_confidence']:.2%} < {CONFIDENCE_WARN:.0%})",
                "detail":    f"{confidence['pct_uncertain']:.1%} des prédictions dans la zone d'incertitude (0.4–0.6)",
                "timestamp": now,
            })

        baseline_rate = training_stats.get("potability_rate", 0.39)
        prod_rate     = confidence.get("potability_rate")
        if prod_rate is not None:
            delta = abs(prod_rate - baseline_rate)
            if delta > POTABILITY_DRIFT_WARN:
                alerts.append({
                    "type":      "prediction_drift",
                    "severity":  "warning",
                    "feature":   None,
                    "message":   f"Dérive du taux de potabilité ({prod_rate:.1%} vs baseline {baseline_rate:.1%})",
                    "detail":    f"Écart de {delta:.1%} — seuil d'alerte : {POTABILITY_DRIFT_WARN:.0%}",
                    "timestamp": now,
                })

    return alerts


def full_report(db, window_days: int = 30) -> dict:
    """Point d'entrée principal : rapport complet drift + confiance + alertes."""
    stats      = _load_training_stats()
    drift      = compute_drift(db, window_days)
    confidence = compute_confidence_metrics(db, window_days)
    alerts     = compute_alerts(drift, confidence, stats)

    # insufficient_data ne déclenche pas de statut critique
    drift_levels = [d["level"] for d in drift.values() if d["level"] != "insufficient_data"]
    global_level = (
        "critical" if "critical" in drift_levels
        else "warn" if "warn" in drift_levels or confidence.get("confidence_level") == "warn"
        else "ok"
    )

    n_insufficient = sum(1 for d in drift.values() if d["level"] == "insufficient_data")

    return {
        "window_days":     window_days,
        "global_status":   global_level,
        "n_alerts":        len(alerts),
        "n_insufficient":  n_insufficient,
        "alerts":          alerts,
        "drift":           drift,
        "confidence":      confidence,
        "baseline": {
            "potability_rate": stats["potability_rate"],
            "n_train_samples": stats["n_samples"],
        },
        "thresholds": {
            "psi_warn":              PSI_WARN,
            "psi_ok":                PSI_OK,
            "min_samples_psi":       MIN_SAMPLES_PSI,
            "confidence_warn":       CONFIDENCE_WARN,
            "potability_drift_warn": POTABILITY_DRIFT_WARN,
        },
    }

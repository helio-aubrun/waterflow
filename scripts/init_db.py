"""
scripts/init_db.py — Initialise la base de données et injecte des données de test.

Usage :
    python scripts/init_db.py            # init + seed (défaut)
    python scripts/init_db.py --init-only  # tables seulement, sans données
    python scripts/init_db.py --reset    # supprime et recrée tout (DANGEREUX en prod)

Clients créés :
    CLIENT-001 / Mairie de Marseille        → clé affichée en sortie
    CLIENT-002 / Syndicat des Eaux du Var   → clé affichée en sortie
    CLIENT-003 / Commune de Nice (inactif)  → clé affichée en sortie
"""

import sys
import os
import json
import secrets
import argparse
import random
from datetime import datetime, timezone, timedelta

import joblib
import numpy as np
import xgboost

# Ajoute la racine du projet au chemin Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.models.db import (
    init_db, SessionLocal, Base, engine,
    Client, Prelevement, Mesure, Prediction, IngestionSource
)

# ── Chargement du vrai modèle (pour de vraies prédictions de test) ──────────
#
# Chargé directement depuis les fichiers (model_artifacts/xgboost_model.json,
# .../robust_scaler.pkl) plutôt que via mlflow.xgboost.load_model(), qui
# exige un registre MLflow ("WaterQualityXGBoost") potentiellement absent ou
# non peuplé sur cette machine (mlflow_water.db est gitignoré, régénéré
# localement). Les artefacts modèle/scaler, eux, sont versionnés — ce chemin
# fonctionne donc dans n'importe quel clone du dépôt.
MODEL_PATH  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "model_artifacts", "xgboost_model.json")
SCALER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "model_artifacts", "robust_scaler.pkl")
MODEL_FEATURES = ["ph", "Hardness", "Solids", "Chloramines", "Sulfate",
                  "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"]

_model  = None
_scaler = None


def _ensure_model_loaded():
    global _model, _scaler
    if _model is not None:
        return
    _model = xgboost.XGBClassifier()
    _model.load_model(MODEL_PATH)
    _scaler = joblib.load(SCALER_PATH)


def _predict_real(m: dict) -> tuple[int, float]:
    """Prédiction reelle via le modele XGBoost entraine (pas une heuristique)."""
    _ensure_model_loaded()
    ordered = {
        "ph": m["ph"], "Hardness": m["hardness"], "Solids": m["solids"],
        "Chloramines": m["chloramines"], "Sulfate": m["sulfate"],
        "Conductivity": m["conductivity"], "Organic_carbon": m["organic_carbon"],
        "Trihalomethanes": m["trihalomethanes"], "Turbidity": m["turbidity"],
    }
    values = np.array([[float(ordered[f]) for f in MODEL_FEATURES]])
    values_scaled = _scaler.transform(values)
    potable = int(_model.predict(values_scaled)[0])
    probability = float(_model.predict_proba(values_scaled)[0][1])
    return potable, round(probability, 4)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Génération de prélèvements synthétiques (monitoring / data drift) ───────
#
# Le monitoring (/exploitation/monitoring) exige au moins MIN_SAMPLES_PSI=50
# mesures non nulles par feature sur la fenêtre choisie pour calculer un PSI
# fiable (cf. api/services/monitoring_service.py) — avec les 5 prélèvements
# ci-dessus, chaque feature reste en "insufficient_data". Ce bloc ajoute des
# prélèvements supplémentaires pour dépasser ce seuil.
#
# Les valeurs sont tirées directement selon les proportions par bin
# (bin_edges / expected_pct) de model_artifacts/training_stats.json — donc
# fidèles à la vraie forme (probablement asymétrique) de la distribution
# d'entraînement — plutôt qu'une loi gaussienne, qui ne respecterait que la
# moyenne et produirait un PSI non nul même sans dérive volontaire.
#
# Toutes les features (Chloramines incluse) suivent fidèlement leur vraie
# distribution d'entraînement : ces prélèvements synthétiques ne simulent
# aucune dérive, ils servent uniquement à dépasser MIN_SAMPLES_PSI pour que
# le monitoring sorte de l'état "insufficient_data".
TRAINING_STATS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "model_artifacts", "training_stats.json",
)

SYNTHETIC_LIEUX = [
    "Suivi continu réseau", "Point de contrôle automatique",
    "Sonde connectée", "Relevé capteur IoT", "Poste de surveillance",
]


def _load_training_stats():
    with open(TRAINING_STATS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _generate_balanced_values(bin_edges, weights, n):
    """Génère exactement n valeurs dont la répartition par bin suit
    fidèlement `weights`, À L'ARRONDI ENTIER PRÈS — plutôt qu'un tirage
    aléatoire indépendant par valeur.

    Un tirage aléatoire par valeur (random.choices répété) introduit un
    bruit d'échantillonnage évitable sur un petit n : même fidèle en
    moyenne, un bin à 10% peut n'en recevoir que 7% ou 13% sur 65 tirages
    par pur hasard, ce qui gonfle le PSI sans vraie dérive. Ici, le nombre
    de valeurs par bin est calculé à l'avance (méthode du plus grand reste,
    comme pour la répartition de sièges) puis réparti aléatoirement dans
    l'intervalle du bin — seule la position DANS le bin reste aléatoire.
    """
    n_bins = len(weights)
    raw_counts = [w * n for w in weights]
    counts = [int(c) for c in raw_counts]
    remainder = n - sum(counts)
    # attribue les unités manquantes aux bins ayant le plus grand reste décimal
    order = sorted(range(n_bins), key=lambda i: raw_counts[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1

    values = []
    for idx, count in enumerate(counts):
        lo, hi = bin_edges[idx], bin_edges[idx + 1]
        values.extend(
            round(random.uniform(lo, hi), 2) if hi > lo else round(lo, 2)
            for _ in range(count)
        )
    random.shuffle(values)
    return values


def _generate_bulk_samples(n=60, client_indices=(0, 1), max_days_ago=25):
    """N prélèvements synthétiques, répartis sur les derniers `max_days_ago`
    jours (donc inclus dans la fenêtre par défaut de 30 jours du monitoring),
    alternés entre les clients donnés."""
    training_stats = _load_training_stats()

    feature_values = {}
    for feat in ("ph", "Hardness", "Solids", "Chloramines", "Sulfate",
                 "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"):
        ref = training_stats["features"][feat]
        feature_values[feat.lower()] = _generate_balanced_values(
            ref["bin_edges"], ref["expected_pct"], n
        )

    out = []
    for i in range(n):
        lieu = f"{random.choice(SYNTHETIC_LIEUX)} #{i + 1:03d}"
        out.append({
            "client_idx": client_indices[i % len(client_indices)],
            "date": utcnow() - timedelta(
                days=random.randint(1, max_days_ago),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            ),
            "lieu": lieu,
            "source": IngestionSource.MANUAL if i % 3 else IngestionSource.OCR,
            "mesures": {feat: vals[i] for feat, vals in feature_values.items()},
        })
    return out


def reset_db():
    print("⚠️  Suppression de toutes les tables...")
    Base.metadata.drop_all(bind=engine)
    print("✓  Tables supprimées.")


def create_tables():
    init_db()
    print("✓  Tables créées (ou déjà existantes).")


def seed(db):
    # ── Clients ────────────────────────────────────────────────────────────────

    clients_data = [
        {
            "id_client":    "CLIENT-001",
            "denomination": "Mairie de Marseille",
            "adresse":      "2 Quai du Port, 13002 Marseille",
            "actif":        True,
        },
        {
            "id_client":    "CLIENT-002",
            "denomination": "Syndicat des Eaux du Var",
            "adresse":      "45 Avenue de la République, 83000 Toulon",
            "actif":        True,
        },
        {
            "id_client":    "CLIENT-003",
            "denomination": "Commune de Nice",
            "adresse":      "5 Rue de l'Hôtel de Ville, 06000 Nice",
            "actif":        False,
        },
    ]

    created_clients = []
    print("\n── Clients ─────────────────────────────────────────────────────────")
    for data in clients_data:
        existing = db.query(Client).filter_by(id_client=data["id_client"]).first()
        if existing:
            print(f"  ⚠  {data['id_client']} déjà présent — ignoré.")
            created_clients.append((existing, None))
            continue

        client = Client(
            id_client=data["id_client"],
            denomination=data["denomination"],
            adresse=data["adresse"],
            actif=data["actif"],
            rgpd_consent=True,
            rgpd_consent_at=utcnow(),
        )
        raw_key = secrets.token_urlsafe(32)
        client.set_api_key(raw_key)
        db.add(client)
        db.flush()
        created_clients.append((client, raw_key))
        status = "actif" if data["actif"] else "inactif"
        print(f"  ✓  {data['id_client']} ({status})")
        print(f"     Clé API : {raw_key}")

    db.commit()

    # ── Prélèvements + Mesures ─────────────────────────────────────────────────

    samples = [
        # CLIENT-001 — 3 prélèvements
        {
            "client_idx": 0,
            "date": utcnow() - timedelta(days=30),
            "lieu": "Station de pompage Nord",
            "source": IngestionSource.MANUAL,
            "mesures": {
                "ph": 7.2, "hardness": 182.5, "solids": 18630.0,
                "chloramines": 8.1, "sulfate": 310.0, "conductivity": 415.0,
                "organic_carbon": 14.2, "trihalomethanes": 66.4, "turbidity": 3.8,
            },
        },
        {
            "client_idx": 0,
            "date": utcnow() - timedelta(days=15),
            "lieu": "Réservoir Sud",
            "source": IngestionSource.OCR,
            "mesures": {
                "ph": 6.8, "hardness": 204.3, "solids": 22450.0,
                "chloramines": 7.5, "sulfate": 285.0, "conductivity": 390.0,
                "organic_carbon": 11.8, "trihalomethanes": 75.2, "turbidity": 4.1,
            },
        },
        {
            "client_idx": 0,
            "date": utcnow() - timedelta(days=2),
            "lieu": "Puits privé Est",
            "source": IngestionSource.MANUAL,
            "mesures": {
                "ph": 8.1, "hardness": 155.0, "solids": 14200.0,
                "chloramines": 9.2, "sulfate": 330.0, "conductivity": 445.0,
                "organic_carbon": 16.0, "trihalomethanes": 58.0, "turbidity": 2.9,
            },
        },
        # CLIENT-002 — 2 prélèvements
        {
            "client_idx": 1,
            "date": utcnow() - timedelta(days=20),
            "lieu": "Source de la Foux",
            "source": IngestionSource.MANUAL,
            "mesures": {
                "ph": 7.5, "hardness": 196.0, "solids": 19800.0,
                "chloramines": 6.8, "sulfate": 270.0, "conductivity": 402.0,
                "organic_carbon": 13.5, "trihalomethanes": 70.1, "turbidity": 3.5,
            },
        },
        {
            "client_idx": 1,
            "date": utcnow() - timedelta(days=5),
            "lieu": "Forage municipal",
            "source": IngestionSource.OCR,
            "mesures": {
                "ph": 5.1, "hardness": 320.0, "solids": 45000.0,
                "chloramines": 12.5, "sulfate": 480.0, "conductivity": 680.0,
                "organic_carbon": 28.0, "trihalomethanes": 120.0, "turbidity": 9.2,
            },
        },
    ]

    print("\n── Prélèvements ─────────────────────────────────────────────────────")
    for s in samples:
        client_obj, _ = created_clients[s["client_idx"]]
        if client_obj is None:
            continue

        existing = db.query(Prelevement).filter_by(
            client_id=client_obj.id,
            date_prelevement=s["date"],
            lieu=s["lieu"],
        ).first()
        if existing:
            print(f"  ⚠  Prélèvement '{s['lieu']}' déjà présent — ignoré.")
            continue

        prev = Prelevement(
            client_id=client_obj.id,
            date_prelevement=s["date"],
            lieu=s["lieu"],
            source=s["source"],
        )
        db.add(prev)
        db.flush()

        m = s["mesures"]
        mesure = Mesure(
            prelevement_id=prev.id,
            ph=m["ph"], hardness=m["hardness"], solids=m["solids"],
            chloramines=m["chloramines"], sulfate=m["sulfate"],
            conductivity=m["conductivity"], organic_carbon=m["organic_carbon"],
            trihalomethanes=m["trihalomethanes"], turbidity=m["turbidity"],
        )
        db.add(mesure)
        db.flush()

        # Vraie prédiction (modèle XGBoost entraîné, cf. _predict_real)
        is_potable, probability = _predict_real(m)
        pred = Prediction(
            prelevement_id=prev.id,
            potable=is_potable,
            probability=probability,
            model_version="xgboost_model.json",
        )
        db.add(pred)

        label = "Potable" if is_potable else "Non potable"
        print(f"  ✓  {client_obj.id_client} — {s['lieu']} ({s['source'].value}) → {label}")

    db.commit()

    # ── Prélèvements synthétiques (pour dépasser MIN_SAMPLES_PSI=50 et
    # démontrer le monitoring avec un vrai statut, cf. FEATURE_STATS ci-dessus) ──

    random.seed(42)  # reproductible d'une exécution à l'autre
    bulk = _generate_bulk_samples(n=60, client_indices=(0, 1))
    n_created, n_skipped = 0, 0

    for s in bulk:
        client_obj, _ = created_clients[s["client_idx"]]
        if client_obj is None:
            continue

        existing = db.query(Prelevement).filter_by(
            client_id=client_obj.id,
            date_prelevement=s["date"],
            lieu=s["lieu"],
        ).first()
        if existing:
            n_skipped += 1
            continue

        prev = Prelevement(
            client_id=client_obj.id,
            date_prelevement=s["date"],
            lieu=s["lieu"],
            source=s["source"],
        )
        db.add(prev)
        db.flush()

        m = s["mesures"]
        mesure = Mesure(
            prelevement_id=prev.id,
            ph=m["ph"], hardness=m["hardness"], solids=m["solids"],
            chloramines=m["chloramines"], sulfate=m["sulfate"],
            conductivity=m["conductivity"], organic_carbon=m["organic_carbon"],
            trihalomethanes=m["trihalomethanes"], turbidity=m["turbidity"],
        )
        db.add(mesure)
        db.flush()

        is_potable, probability = _predict_real(m)
        db.add(Prediction(
            prelevement_id=prev.id,
            potable=is_potable,
            probability=probability,
            model_version="xgboost_model.json",
        ))
        n_created += 1

    db.commit()
    print("\n── Prélèvements synthétiques (monitoring) ───────────────────────────")
    print(f"  ✓  {n_created} prélèvements générés (dérive volontaire sur Chloramines)"
          + (f", {n_skipped} déjà présents ignorés" if n_skipped else ""))


def main():
    parser = argparse.ArgumentParser(description="Initialise la base Waterflow 2")
    parser.add_argument("--init-only", action="store_true",
                        help="Crée les tables sans insérer de données")
    parser.add_argument("--reset", action="store_true",
                        help="Supprime et recrée toutes les tables (DANGEREUX)")
    args = parser.parse_args()

    print("═" * 60)
    print("  Waterflow 2 — Initialisation base de données")
    print("═" * 60)

    if args.reset:
        confirm = input("⚠️  Supprimer toutes les données ? (oui/non) : ").strip().lower()
        if confirm != "oui":
            print("Annulé.")
            sys.exit(0)
        reset_db()

    create_tables()

    if not args.init_only:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()

    print("\n═" * 60)
    print("  Terminé.")
    print("═" * 60)


if __name__ == "__main__":
    main()

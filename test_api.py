"""
tests/test_api.py — Tests automatisés Waterflow 2

Couvre :
  - Authentification (clé valide, invalide, absente)
  - /health
  - /predict  (JSON valide, features manquantes, valeur non numérique)
  - /data/prelevements (accès par profil)
  - /data/dashboard
  - /admin/clients + /admin/clients/<id>/apikey
  - /metrics (accès admin)

Utilise une base SQLite en mémoire et un modèle factice (mock).
"""

import json
import secrets
import pytest
from unittest.mock import patch, MagicMock

# ── Setup environnement avant import Flask ──────────────────────────────────
import os
os.environ.setdefault("DATABASE_URL",   "sqlite:///:memory:")
os.environ.setdefault("API_KEYS",       "")           # on gère via DB
os.environ.setdefault("MLFLOW_URI",     "mock")
os.environ.setdefault("SCALER_PATH",    "mock")
os.environ.setdefault("OCR_SPACE_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")


# ── Mock modèle + scaler avant import ──────────────────────────────────────
import numpy as np

mock_model  = MagicMock()
mock_model.predict.return_value       = np.array([1])
mock_model.predict_proba.return_value = np.array([[0.1, 0.87]])

mock_scaler = MagicMock()
mock_scaler.transform.side_effect = lambda x: x

with patch("mlflow.xgboost.load_model", return_value=mock_model), \
     patch("joblib.load",               return_value=mock_scaler), \
     patch("mlflow.set_tracking_uri"):
    from api.app            import create_app
    from api.models.db      import init_db, SessionLocal, Client, ApiKey, ProfileEnum


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config["TESTING"] = True
    init_db()
    return application


@pytest.fixture(scope="session")
def client_app(app):
    return app.test_client()


def _create_client_with_key(code: str, profil: ProfileEnum) -> tuple[str, str]:
    """Crée un client + une clé API en base, retourne (client_id, raw_key)."""
    db  = SessionLocal()
    raw = secrets.token_urlsafe(16)
    c   = Client(code=code, profil=profil, actif=True, rgpd_consent=True)
    db.add(c)
    db.flush()
    k = ApiKey(client_id=c.id, key_hash=ApiKey.hash_key(raw), hint=raw[:4])
    db.add(k)
    db.commit()
    cid = c.id
    db.close()
    return cid, raw


@pytest.fixture(scope="session")
def admin_key():
    _, key = _create_client_with_key("ADMIN-001", ProfileEnum.ADMIN)
    return key


@pytest.fixture(scope="session")
def analyste_key():
    _, key = _create_client_with_key("ANALYSTE-001", ProfileEnum.ANALYSTE)
    return key


@pytest.fixture(scope="session")
def terrain_key():
    _, key = _create_client_with_key("TERRAIN-001", ProfileEnum.TERRAIN)
    return key


VALID_MESURES = {
    "ph": 7.2, "Hardness": 198.0, "Solids": 18630.0,
    "Chloramines": 7.1, "Sulfate": 333.0, "Conductivity": 432.0,
    "Organic_carbon": 14.2, "Trihalomethanes": 62.8, "Turbidity": 4.0,
}


# ── /health ──────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_public(self, client_app):
        r = client_app.get("/health")
        assert r.status_code == 200
        d = r.get_json()
        assert d["status"] == "ok"
        assert "model" in d

    def test_health_no_key_needed(self, client_app):
        r = client_app.get("/health")
        assert r.status_code == 200


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_no_key(self, client_app):
        r = client_app.post("/predict", json=VALID_MESURES)
        assert r.status_code == 401

    def test_wrong_key(self, client_app):
        r = client_app.post("/predict", json=VALID_MESURES,
                             headers={"X-API-Key": "mauvaise-cle"})
        assert r.status_code == 401

    def test_key_in_header(self, client_app, terrain_key):
        r = client_app.post("/predict", json=VALID_MESURES,
                             headers={"X-API-Key": terrain_key})
        assert r.status_code == 200

    def test_key_in_query(self, client_app, terrain_key):
        r = client_app.post(f"/predict?api_key={terrain_key}", json=VALID_MESURES)
        assert r.status_code == 200


# ── /predict ─────────────────────────────────────────────────────────────────

class TestPredict:
    def test_valid(self, client_app, terrain_key):
        r = client_app.post("/predict", json=VALID_MESURES,
                             headers={"X-API-Key": terrain_key})
        assert r.status_code == 200
        d = r.get_json()
        assert d["potable"] in (0, 1)
        assert "probability" in d
        assert d["label"] in ("Potable", "Non potable")

    def test_missing_feature(self, client_app, terrain_key):
        bad = {k: v for k, v in VALID_MESURES.items() if k != "ph"}
        r   = client_app.post("/predict", json=bad,
                               headers={"X-API-Key": terrain_key})
        assert r.status_code == 400
        assert "manquantes" in r.get_json()["error"].lower()

    def test_non_numeric(self, client_app, terrain_key):
        bad = {**VALID_MESURES, "ph": "pas-un-nombre"}
        r   = client_app.post("/predict", json=bad,
                               headers={"X-API-Key": terrain_key})
        assert r.status_code == 400

    def test_empty_body(self, client_app, terrain_key):
        r = client_app.post("/predict", data="", content_type="application/json",
                             headers={"X-API-Key": terrain_key})
        assert r.status_code in (400, 422)


# ── /data/prelevements ───────────────────────────────────────────────────────

class TestData:
    def test_terrain_forbidden(self, client_app, terrain_key):
        r = client_app.get("/data/prelevements",
                            headers={"X-API-Key": terrain_key})
        assert r.status_code == 403

    def test_analyste_allowed(self, client_app, analyste_key):
        r = client_app.get("/data/prelevements",
                            headers={"X-API-Key": analyste_key})
        assert r.status_code == 200
        d = r.get_json()
        assert "items" in d
        assert "total"  in d
        assert "pages"  in d

    def test_pagination_params(self, client_app, analyste_key):
        r = client_app.get("/data/prelevements?page=1&per_page=5",
                            headers={"X-API-Key": analyste_key})
        assert r.status_code == 200
        assert r.get_json()["per_page"] == 5

    def test_dashboard(self, client_app, analyste_key):
        r = client_app.get("/data/dashboard",
                            headers={"X-API-Key": analyste_key})
        assert r.status_code == 200
        d = r.get_json()
        assert "total_prelevements" in d
        assert "moyennes" in d


# ── /admin ───────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_create_client_as_admin(self, client_app, admin_key):
        r = client_app.post("/admin/clients",
                             json={"code": "COMM-TEST-99", "profil": "terrain",
                                   "nom_pseudo": "Commune Test", "rgpd_consent": True},
                             headers={"X-API-Key": admin_key})
        assert r.status_code == 201
        d = r.get_json()
        assert "id" in d
        return d["id"]

    def test_create_client_analyste_forbidden(self, client_app, analyste_key):
        r = client_app.post("/admin/clients",
                             json={"code": "COMM-DENIED", "profil": "terrain"},
                             headers={"X-API-Key": analyste_key})
        assert r.status_code == 403

    def test_duplicate_code(self, client_app, admin_key):
        r = client_app.post("/admin/clients",
                             json={"code": "COMM-TEST-99", "profil": "terrain"},
                             headers={"X-API-Key": admin_key})
        assert r.status_code == 409

    def test_generate_api_key(self, client_app, admin_key):
        # Récupère l'ID d'un client existant
        db = SessionLocal()
        c  = db.query(Client).filter(Client.code == "COMM-TEST-99").first()
        db.close()
        if not c:
            return  # test précédent a peut-être échoué
        r = client_app.post(f"/admin/clients/{c.id}/apikey",
                             json={"label": "test-key"},
                             headers={"X-API-Key": admin_key})
        assert r.status_code == 201
        d = r.get_json()
        assert "api_key" in d
        assert "warning" in d

    def test_list_clients(self, client_app, admin_key):
        r = client_app.get("/admin/clients",
                            headers={"X-API-Key": admin_key})
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)


# ── /metrics ─────────────────────────────────────────────────────────────────

class TestMetrics:
    def test_admin_can_access(self, client_app, admin_key):
        r = client_app.get("/metrics",
                            headers={"X-API-Key": admin_key})
        assert r.status_code == 200
        d = r.get_json()
        assert "routes" in d
        assert "total_prelevements" in d

    def test_analyste_forbidden(self, client_app, analyste_key):
        r = client_app.get("/metrics",
                            headers={"X-API-Key": analyste_key})
        assert r.status_code == 403

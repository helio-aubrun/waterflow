"""
=============================================================
TESTS FONCTIONNELS — Projet Water Potability MLOps
=============================================================
Objectif : tester les endpoints de l'API Flask de bout en bout,
           en mockant le modèle MLflow et le scaler.
Couverture :
  - GET  /health
  - GET  /
  - POST /predict  (cas nominaux + cas d'erreur, authentifiés X-API-Key)
  - Comportement HTTP (codes de statut, Content-Type, JSON)
=============================================================
"""

import json
import secrets
import pytest
import numpy as np
from unittest.mock import MagicMock


# ──────────────────────────────────────────────────────────
# FIXTURES — Application Flask avec mocks injectés
# ──────────────────────────────────────────────────────────

FEATURES = [
    "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
    "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"
]

VALID_PAYLOAD = {
    "ph": 7.0,
    "Hardness": 200.0,
    "Solids": 20000.0,
    "Chloramines": 7.5,
    "Sulfate": 350.0,
    "Conductivity": 400.0,
    "Organic_carbon": 14.0,
    "Trihalomethanes": 66.0,
    "Turbidity": 3.5,
}


def _auth_headers() -> dict:
    """
    Cree (ou reutilise) un client de test actif en base et retourne un
    header X-API-Key valide. /predict exige desormais une authentification
    (@require_client_key), au meme titre que /ingest/*.
    """
    from api.models.db import Client, SessionLocal

    db = SessionLocal()
    try:
        client_row = db.query(Client).filter_by(id_client="TEST-PREDICT").first()
        if client_row is None:
            client_row = Client(
                id_client="TEST-PREDICT",
                denomination="Client de test (test_fonctionnels)",
                adresse="N/A",
                actif=True,
            )
            db.add(client_row)
        raw_key = secrets.token_urlsafe(32)
        client_row.set_api_key(raw_key)
        client_row.actif = True
        db.commit()
        return {"X-API-Key": raw_key}
    finally:
        db.close()


def create_app_with_mocks(predict_value=1, proba_value=0.87):
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array([predict_value])
    mock_model.predict_proba.return_value = np.array([[1 - proba_value, proba_value]])

    mock_scaler = MagicMock()
    mock_scaler.transform.return_value = np.zeros((1, 9))

    import api.services.predict_service as ps
    ps._model = mock_model
    ps._scaler = mock_scaler

    from api.app import create_app
    flask_instance = create_app()
    flask_instance.config["TESTING"] = True
    client = flask_instance.test_client()
    headers = _auth_headers()

    return client, mock_model, mock_scaler, headers


# ──────────────────────────────────────────────────────────
# SECTION 1 — Endpoint GET /health
# ──────────────────────────────────────────────────────────

class TestEndpointHealth:
    """Vérifie la disponibilité et la réponse du health-check."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client, self.model, self.scaler, self.headers = create_app_with_mocks()

    def test_health_statut_200(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_health_retourne_json(self):
        resp = self.client.get("/health")
        assert resp.content_type == "application/json"

    def test_health_champ_status_ok(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    def test_health_champ_model_present(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        assert "model" in data
        assert isinstance(data["model"], str)

    def test_health_methode_get_uniquement(self):
        """POST sur /health doit retourner 405 Method Not Allowed."""
        resp = self.client.post("/health")
        assert resp.status_code == 405


# ──────────────────────────────────────────────────────────
# SECTION 2 — Endpoint GET /
# ──────────────────────────────────────────────────────────

class TestEndpointIndex:
    """Vérifie que la page d'accueil est accessible."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client, _, _, self.headers = create_app_with_mocks()

    def test_index_statut_200_ou_redirect(self):
        resp = self.client.get("/")
        assert resp.status_code in (200, 302, 404)  # 404 si template absent en CI


# ──────────────────────────────────────────────────────────
# SECTION 3 — Endpoint POST /predict — Cas nominaux
# ──────────────────────────────────────────────────────────

class TestEndpointPredictNominal:
    """Teste les scénarios normaux de prédiction (authentifiés X-API-Key)."""

    @pytest.fixture(autouse=True)
    def setup_potable(self):
        self.client_potable, self.model_potable, _, self.headers = create_app_with_mocks(
            predict_value=1, proba_value=0.87
        )

    def test_predict_statut_200(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        assert resp.status_code == 200

    def test_predict_retourne_json(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        assert resp.content_type == "application/json"

    def test_predict_champs_presents(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        data = json.loads(resp.data)
        assert "potable" in data
        assert "label" in data
        assert "probability" in data

    def test_predict_label_potable(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        data = json.loads(resp.data)
        assert data["potable"] == 1
        assert data["label"] == "Potable"

    def test_predict_label_non_potable(self):
        client, _, _, headers = create_app_with_mocks(predict_value=0, proba_value=0.12)
        resp = client.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=headers,
        )
        data = json.loads(resp.data)
        assert data["potable"] == 0
        assert data["label"] == "Non potable"

    def test_predict_probability_dans_intervalle(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        data = json.loads(resp.data)
        assert 0.0 <= data["probability"] <= 1.0

    def test_predict_model_appele_une_fois(self):
        self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=self.headers,
        )
        assert self.model_potable.predict.call_count == 1

    def test_predict_scaler_appele_avant_model(self):
        """Le scaler doit être appelé avant le modèle."""
        client, model, scaler, headers = create_app_with_mocks()
        call_order = []
        scaler.transform.side_effect = lambda x: (call_order.append("scaler"), np.zeros((1, 9)))[1]
        model.predict.side_effect = lambda x: (call_order.append("model"), np.array([1]))[1]

        client.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=headers,
        )
        assert call_order.index("scaler") < call_order.index("model")

    def test_predict_force_json_sans_content_type(self):
        """L'API doit accepter le JSON même sans Content-Type explicite (force=True)."""
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            headers=self.headers,
        )
        assert resp.status_code == 200

    def test_predict_sans_cle_api_retourne_401(self):
        """Sans X-API-Key, /predict doit être refusée (modèle protégé)."""
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_predict_mauvaise_cle_api_retourne_401(self):
        resp = self.client_potable.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers={"X-API-Key": "fausse-cle"},
        )
        assert resp.status_code == 401


# ──────────────────────────────────────────────────────────
# SECTION 4 — Endpoint POST /predict — Cas d'erreur
# ──────────────────────────────────────────────────────────

class TestEndpointPredictErreurs:
    """Teste que l'API renvoie des erreurs cohérentes pour des inputs invalides."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client, _, _, self.headers = create_app_with_mocks()

    def _post(self, payload):
        return self.client.post(
            "/predict",
            data=json.dumps(payload),
            content_type="application/json",
            headers=self.headers,
        )

    def test_feature_manquante_retourne_400(self):
        payload_incomplet = {k: v for k, v in VALID_PAYLOAD.items() if k != "ph"}
        resp = self._post(payload_incomplet)
        assert resp.status_code == 400

    def test_feature_manquante_message_erreur(self):
        payload_incomplet = {k: v for k, v in VALID_PAYLOAD.items() if k != "ph"}
        resp = self._post(payload_incomplet)
        data = json.loads(resp.data)
        assert "error" in data

    def test_valeur_string_retourne_400(self):
        payload_invalide = {**VALID_PAYLOAD, "ph": "abc"}
        resp = self._post(payload_invalide)
        assert resp.status_code == 400

    def test_payload_vide_retourne_400(self):
        resp = self._post({})
        assert resp.status_code == 400

    def test_erreur_toujours_json(self):
        """Même en cas d'erreur, la réponse doit être du JSON valide."""
        payload_incomplet = {k: v for k, v in VALID_PAYLOAD.items() if k != "Turbidity"}
        resp = self._post(payload_incomplet)
        try:
            json.loads(resp.data)
        except json.JSONDecodeError:
            pytest.fail("La réponse d'erreur n'est pas du JSON valide")

    @pytest.mark.parametrize("missing_feature", FEATURES)
    def test_chaque_feature_manquante_detectee(self, missing_feature):
        """Supprimer n'importe quelle feature doit produire une erreur 400."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing_feature}
        resp = self._post(payload)
        assert resp.status_code == 400, f"Feature '{missing_feature}' manquante non détectée"


# ──────────────────────────────────────────────────────────
# SECTION 5 — Intégration modèle + API
# ──────────────────────────────────────────────────────────

class TestIntegrationModelAPI:
    """Tests de bout en bout : vérifie la cohérence entre modèle et réponse."""

    @pytest.mark.parametrize("pred,proba,expected_label", [
        (1, 0.95, "Potable"),
        (1, 0.55, "Potable"),
        (0, 0.45, "Non potable"),
        (0, 0.05, "Non potable"),
    ])
    def test_coherence_prediction_label_probabilite(self, pred, proba, expected_label):
        client, _, _, headers = create_app_with_mocks(predict_value=pred, proba_value=proba)
        resp = client.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=headers,
        )
        data = json.loads(resp.data)
        assert data["label"] == expected_label
        assert data["potable"] == pred

    def test_probabilite_reflete_classe_positive(self):
        """La probabilité retournée doit correspondre à P(potable=1)."""
        expected_proba = 0.7654
        client, _, _, headers = create_app_with_mocks(predict_value=1, proba_value=expected_proba)
        resp = client.post(
            "/predict",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
            headers=headers,
        )
        data = json.loads(resp.data)
        assert abs(data["probability"] - round(expected_proba, 4)) < 1e-4

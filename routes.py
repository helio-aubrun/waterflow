"""
api/routes/routes.py — Toutes les routes Waterflow 2

Profils d'accès :
  terrain  → /ocr, /ocr-and-predict, /predict (POST)
  analyste → tout terrain + /data/...  (lecture)
  admin    → tout + gestion clients/clés
  readonly → /data/... en lecture seule

Routes :
  GET  /health
  GET  /metrics                    ← monitoring (admin)

  POST /predict                    ← prédiction JSON
  POST /ocr                        ← extraction fiche
  POST /ocr-and-predict            ← pipeline complet

  GET  /data/prelevements          ← liste paginée (analyste+)
  GET  /data/prelevements/<id>     ← détail (analyste+)
  GET  /data/dashboard             ← KPIs (analyste+)

  POST /admin/clients              ← créer client (admin)
  POST /admin/clients/<id>/apikey  ← générer clé (admin)
  GET  /admin/clients              ← lister clients (admin)
"""

import json
import time
import secrets
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from api.models.db       import (
    Client, ApiKey, Prelevement, Mesure, Prediction,
    ProfileEnum, IngestionSourceEnum, get_db, utcnow, RequestMetric
)
from api.middleware.auth import (
    require_api_key, require_profile, log_audit, record_metric
)
from api.services.ocr_service     import extract_from_document, ACCEPTED_MIME
from api.services.predict_service import run_prediction, MLFLOW_MODEL_URI

logger = logging.getLogger(__name__)
bp     = Blueprint("api", __name__)

MAX_UPLOAD_BYTES = int(__import__("os").getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024


# ── Utilitaires ─────────────────────────────────────────────────────────────

def _timed_response(fn):
    """Mesure le temps d'une route et enregistre la métrique."""
    def wrapper(*args, **kwargs):
        t0     = time.perf_counter()
        result = fn(*args, **kwargs)
        code   = result[1] if isinstance(result, tuple) else 200
        record_metric(
            route       = request.path,
            method      = request.method,
            status_code = code,
            duration_ms = (time.perf_counter() - t0) * 1000,
            client_hint = getattr(g, "key_hint", None),
        )
        return result
    wrapper.__name__ = fn.__name__
    return wrapper


def _read_upload():
    if "file" not in request.files:
        raise ValueError("Champ 'file' manquant (multipart/form-data).")
    upload = request.files["file"]
    mime   = (upload.content_type or "").lower().split(";")[0].strip()
    if mime not in ACCEPTED_MIME:
        raise ValueError(
            f"Type non supporté : '{mime}'. "
            f"Acceptés : {', '.join(sorted(ACCEPTED_MIME))}."
        )
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Fichier trop grand (max {MAX_UPLOAD_BYTES // (1024*1024)} Mo).")
    return data, mime, upload.filename or "document"


def _save_prelevement(db, client, extracted: dict, filename: str, mime: str,
                      source: IngestionSourceEnum) -> Prelevement:
    """Persiste un prélèvement + ses mesures depuis un dict extrait."""
    date_str = extracted.get("date_prelevement")
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.fromisoformat(date_str)
        except ValueError:
            pass

    prev = Prelevement(
        client_id        = client.id,
        date_prelevement = date_obj,
        lieu             = extracted.get("lieu"),
        source           = source,
        fichier_nom      = filename,
        fichier_type     = mime,
        ocr_raw_text     = extracted.get("raw_text"),
        ocr_warnings     = json.dumps(extracted.get("warnings", []), ensure_ascii=False),
        observations     = extracted.get("observations"),
    )
    db.add(prev)
    db.flush()

    m = extracted.get("mesures", {})
    mesure = Mesure(
        prelevement_id  = prev.id,
        ph              = m.get("ph"),
        hardness        = m.get("Hardness"),
        solids          = m.get("Solids"),
        chloramines     = m.get("Chloramines"),
        sulfate         = m.get("Sulfate"),
        conductivity    = m.get("Conductivity"),
        organic_carbon  = m.get("Organic_carbon"),
        trihalomethanes = m.get("Trihalomethanes"),
        turbidity       = m.get("Turbidity"),
    )
    db.add(mesure)
    db.commit()
    db.refresh(prev)
    return prev


def _prelevement_to_dict(prev: Prelevement) -> dict:
    m = prev.mesures
    preds = prev.predictions
    last_pred = preds[-1] if preds else None
    return {
        "id":               prev.id,
        "client_id":        prev.client_id,
        "date_prelevement": prev.date_prelevement.isoformat() if prev.date_prelevement else None,
        "lieu":             prev.lieu,
        "source":           prev.source.value if prev.source else None,
        "observations":     prev.observations,
        "created_at":       prev.created_at.isoformat() if prev.created_at else None,
        "warnings":         json.loads(prev.ocr_warnings) if prev.ocr_warnings else [],
        "mesures":          m.to_feature_dict() if m else {},
        "prediction": {
            "potable":     last_pred.potable,
            "label":       "Potable" if last_pred.potable == 1 else "Non potable",
            "probability": last_pred.probability,
            "model":       last_pred.model_version,
            "at":          last_pred.created_at.isoformat(),
        } if last_pred else None,
    }


# ── Santé ────────────────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model":  MLFLOW_MODEL_URI,
        "ts":     utcnow().isoformat(),
    })


# ── Métriques monitoring ─────────────────────────────────────────────────────

@bp.route("/metrics", methods=["GET"])
@require_api_key
@require_profile("admin")
def metrics():
    """
    Indicateurs de santé : erreurs, temps de réponse, volume.
    Accès admin uniquement.
    """
    db   = g.db
    rows = db.query(RequestMetric).order_by(RequestMetric.timestamp.desc()).limit(5000).all()

    from collections import defaultdict
    by_route = defaultdict(lambda: {"count": 0, "errors": 0, "durations": []})
    for r in rows:
        key = f"{r.method} {r.route}"
        by_route[key]["count"] += 1
        if r.status_code >= 400:
            by_route[key]["errors"] += 1
        by_route[key]["durations"].append(r.duration_ms)

    summary = {}
    for route, d in by_route.items():
        durs = d["durations"]
        summary[route] = {
            "count":       d["count"],
            "errors":      d["errors"],
            "error_rate":  round(d["errors"] / d["count"], 4) if d["count"] else 0,
            "p50_ms":      round(sorted(durs)[len(durs)//2], 1) if durs else 0,
            "p95_ms":      round(sorted(durs)[int(len(durs)*.95)], 1) if durs else 0,
            "avg_ms":      round(sum(durs)/len(durs), 1) if durs else 0,
        }

    total_prelevements = db.query(Prelevement).count()
    total_predictions  = db.query(Prediction).count()
    potable_count      = db.query(Prediction).filter(Prediction.potable == 1).count()

    return jsonify({
        "routes":            summary,
        "total_prelevements": total_prelevements,
        "total_predictions":  total_predictions,
        "potable_rate":       round(potable_count / total_predictions, 4)
                              if total_predictions else None,
    })


# ── Prédiction JSON ──────────────────────────────────────────────────────────

@bp.route("/predict", methods=["POST"])
@require_api_key
@_timed_response
def predict():
    """Prédiction à partir d'un JSON de mesures (saisie manuelle)."""
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps JSON attendu."}), 400

    try:
        result = run_prediction(data)
    except ValueError as e:
        log_audit("predict", status_code=400, detail=str(e))
        return jsonify({"error": str(e)}), 400

    # Persistance si prelevement_id fourni
    prelevement_id = data.get("prelevement_id")
    if prelevement_id:
        db = g.db
        pred = Prediction(
            prelevement_id = prelevement_id,
            potable        = result["potable"],
            probability    = result["probability"],
            model_version  = result["model_version"],
        )
        db.add(pred)
        try:
            db.commit()
        except Exception:
            db.rollback()

    log_audit("predict", resource_id=prelevement_id, status_code=200)
    return jsonify(result)


# ── OCR ──────────────────────────────────────────────────────────────────────

@bp.route("/ocr", methods=["POST"])
@require_api_key
@_timed_response
def ocr():
    """Extraction OCR d'une fiche (image ou PDF). Persiste le prélèvement."""
    try:
        file_bytes, mime, filename = _read_upload()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        extracted = extract_from_document(file_bytes, mime)
    except RuntimeError as e:
        log_audit("ocr", status_code=503, detail=str(e))
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        logger.exception("Erreur OCR")
        log_audit("ocr", status_code=500, detail=str(e))
        return jsonify({"error": f"Erreur extraction : {e}"}), 500

    db   = g.db
    prev = _save_prelevement(db, g.client, extracted, filename, mime, IngestionSourceEnum.OCR)
    log_audit("ocr", resource_id=prev.id, status_code=201)

    return jsonify({**extracted, "prelevement_id": prev.id}), 201


# ── OCR + Prédiction ─────────────────────────────────────────────────────────

@bp.route("/ocr-and-predict", methods=["POST"])
@require_api_key
@_timed_response
def ocr_and_predict():
    """Pipeline complet : OCR → persistance → prédiction."""
    try:
        file_bytes, mime, filename = _read_upload()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        extracted = extract_from_document(file_bytes, mime)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        logger.exception("Erreur OCR")
        return jsonify({"error": f"Erreur extraction : {e}"}), 500

    db   = g.db
    prev = _save_prelevement(db, g.client, extracted, filename, mime, IngestionSourceEnum.OCR)

    prediction        = None
    prediction_error  = None
    prediction_possible = False

    try:
        result = run_prediction(extracted.get("mesures", {}))
        pred   = Prediction(
            prelevement_id = prev.id,
            potable        = result["potable"],
            probability    = result["probability"],
            model_version  = result["model_version"],
        )
        db.add(pred)
        db.commit()
        prediction          = result
        prediction_possible = True
    except ValueError as e:
        prediction_error = str(e)
        db.rollback()

    log_audit("ocr_and_predict", resource_id=prev.id, status_code=201)
    return jsonify({
        "prelevement_id":     prev.id,
        "ocr":                extracted,
        "prediction":         prediction,
        "prediction_possible": prediction_possible,
        "prediction_error":   prediction_error,
    }), 201


# ── Données ──────────────────────────────────────────────────────────────────

@bp.route("/data/prelevements", methods=["GET"])
@require_api_key
@require_profile("analyste", "admin", "readonly")
@_timed_response
def list_prelevements():
    """
    Liste paginée des prélèvements.
    Filtres query : client_id, potable (0/1), date_from, date_to, page, per_page
    """
    db       = g.db
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    query    = db.query(Prelevement)

    # Filtre par client (analyste ne voit que les siens, admin voit tout)
    if g.client.profil not in ("admin",):
        query = query.filter(Prelevement.client_id == g.client.id)
    elif request.args.get("client_id"):
        query = query.filter(Prelevement.client_id == request.args["client_id"])

    if request.args.get("date_from"):
        try:
            query = query.filter(
                Prelevement.date_prelevement >= datetime.fromisoformat(request.args["date_from"])
            )
        except ValueError:
            pass

    if request.args.get("date_to"):
        try:
            query = query.filter(
                Prelevement.date_prelevement <= datetime.fromisoformat(request.args["date_to"])
            )
        except ValueError:
            pass

    total  = query.count()
    items  = query.order_by(Prelevement.created_at.desc()) \
                  .offset((page - 1) * per_page).limit(per_page).all()

    log_audit("read_prelevements", status_code=200)
    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    -(-total // per_page),
        "items":    [_prelevement_to_dict(p) for p in items],
    })


@bp.route("/data/prelevements/<string:prev_id>", methods=["GET"])
@require_api_key
@require_profile("analyste", "admin", "readonly")
@_timed_response
def get_prelevement(prev_id: str):
    db   = g.db
    prev = db.query(Prelevement).filter(Prelevement.id == prev_id).first()
    if not prev:
        return jsonify({"error": "Prélèvement introuvable."}), 404

    # Un analyste ne peut voir que ses prélèvements
    if g.client.profil not in ("admin",) and prev.client_id != g.client.id:
        return jsonify({"error": "Accès refusé."}), 403

    log_audit("read_prelevement", resource_id=prev_id, status_code=200)
    return jsonify(_prelevement_to_dict(prev))


@bp.route("/data/dashboard", methods=["GET"])
@require_api_key
@require_profile("analyste", "admin")
@_timed_response
def dashboard():
    """KPIs agrégés pour le tableau de bord qualité."""
    db = g.db

    base = db.query(Prelevement)
    if g.client.profil != "admin":
        base = base.filter(Prelevement.client_id == g.client.id)

    total         = base.count()
    avec_pred     = base.join(Prediction, isouter=True) \
                        .filter(Prediction.id.isnot(None)).count()
    potables      = db.query(Prediction).filter(Prediction.potable == 1).count()
    non_potables  = db.query(Prediction).filter(Prediction.potable == 0).count()
    total_preds   = potables + non_potables

    # Moyennes des mesures
    from sqlalchemy import func
    avgs = db.query(
        func.avg(Mesure.ph).label("ph"),
        func.avg(Mesure.turbidity).label("turbidity"),
        func.avg(Mesure.conductivity).label("conductivity"),
        func.avg(Mesure.chloramines).label("chloramines"),
    ).scalar_many() if False else db.query(
        func.avg(Mesure.ph),
        func.avg(Mesure.turbidity),
        func.avg(Mesure.conductivity),
        func.avg(Mesure.chloramines),
    ).one()

    # 10 derniers prélèvements
    recents = base.order_by(Prelevement.created_at.desc()).limit(10).all()

    log_audit("read_dashboard", status_code=200)
    return jsonify({
        "total_prelevements":  total,
        "avec_prediction":     avec_pred,
        "potable_count":       potables,
        "non_potable_count":   non_potables,
        "potable_rate":        round(potables / total_preds, 4) if total_preds else None,
        "moyennes": {
            "ph":          round(avgs[0], 3) if avgs[0] else None,
            "turbidity":   round(avgs[1], 3) if avgs[1] else None,
            "conductivity":round(avgs[2], 3) if avgs[2] else None,
            "chloramines": round(avgs[3], 3) if avgs[3] else None,
        },
        "recents": [_prelevement_to_dict(p) for p in recents],
    })


# ── Administration ───────────────────────────────────────────────────────────

@bp.route("/admin/clients", methods=["POST"])
@require_api_key
@require_profile("admin")
def create_client():
    data = request.get_json(force=True)
    required = ["code", "profil"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Champs manquants : {missing}"}), 400

    if data["profil"] not in [p.value for p in ProfileEnum]:
        return jsonify({"error": f"Profil invalide. Valeurs : {[p.value for p in ProfileEnum]}"}), 400

    db = g.db
    if db.query(Client).filter(Client.code == data["code"]).first():
        return jsonify({"error": f"Code client déjà existant : {data['code']}"}), 409

    client = Client(
        code         = data["code"],
        nom_pseudo   = data.get("nom_pseudo"),
        email_hash   = Client.hash_email(data["email"]) if data.get("email") else None,
        profil       = ProfileEnum(data["profil"]),
        rgpd_consent = data.get("rgpd_consent", False),
        rgpd_consent_at = utcnow() if data.get("rgpd_consent") else None,
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    log_audit("create_client", resource_id=client.id, status_code=201)
    return jsonify({"id": client.id, "code": client.code, "profil": client.profil}), 201


@bp.route("/admin/clients", methods=["GET"])
@require_api_key
@require_profile("admin")
def list_clients():
    db      = g.db
    clients = db.query(Client).filter(Client.actif == True).all()
    return jsonify([{
        "id":        c.id,
        "code":      c.code,
        "profil":    c.profil,
        "actif":     c.actif,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in clients])


@bp.route("/admin/clients/<string:client_id>/apikey", methods=["POST"])
@require_api_key
@require_profile("admin")
def generate_api_key(client_id: str):
    """Génère une nouvelle clé API pour un client. La clé brute n'est retournée qu'une fois."""
    db     = g.db
    client = db.query(Client).filter(Client.id == client_id, Client.actif == True).first()
    if not client:
        return jsonify({"error": "Client introuvable."}), 404

    data    = request.get_json(force=True) or {}
    raw_key = secrets.token_urlsafe(32)

    api_key = ApiKey(
        client_id  = client.id,
        key_hash   = ApiKey.hash_key(raw_key),
        hint       = raw_key[:4],
        label      = data.get("label", ""),
        expires_at = datetime.fromisoformat(data["expires_at"])
                     if data.get("expires_at") else None,
    )
    db.add(api_key)
    db.commit()

    log_audit("generate_api_key", resource_id=client_id, status_code=201)
    return jsonify({
        "key_id":  api_key.id,
        "api_key": raw_key,     # ← affiché une seule fois
        "hint":    api_key.hint,
        "label":   api_key.label,
        "warning": "Conservez cette clé : elle ne sera plus affichée.",
    }), 201

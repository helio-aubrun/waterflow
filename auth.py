"""
api/middleware/auth.py — Authentification par clé API multi-profil

La clé est résolue contre la table api_keys en base.
Le profil du client est injecté dans flask.g pour contrôle d'accès par route.
"""

import time
import logging
from functools import wraps

from flask import request, jsonify, g
from sqlalchemy.orm import Session

from api.models.db import ApiKey, Client, AuditLog, RequestMetric, get_db, utcnow

logger = logging.getLogger(__name__)


# ── Résolution de clé ───────────────────────────────────────────────────────

def resolve_api_key(raw_key: str | None, db: Session) -> tuple[Client | None, ApiKey | None]:
    """
    Retourne (client, api_key) si la clé est valide et active, (None, None) sinon.
    Met à jour last_used sur la clé.
    """
    if not raw_key:
        return None, None

    key_hash = ApiKey.hash_key(raw_key)
    api_key  = (
        db.query(ApiKey)
          .filter(ApiKey.key_hash == key_hash, ApiKey.actif == True)
          .first()
    )
    if not api_key:
        return None, None

    # Vérification expiration
    if api_key.expires_at and api_key.expires_at < utcnow():
        return None, None

    # Vérification client actif
    client = db.query(Client).filter(Client.id == api_key.client_id, Client.actif == True).first()
    if not client:
        return None, None

    # Mise à jour last_used (sans bloquer)
    try:
        api_key.last_used = utcnow()
        db.commit()
    except Exception:
        db.rollback()

    return client, api_key


# ── Décorateurs ─────────────────────────────────────────────────────────────

def require_api_key(f):
    """
    Décorateur — authentifie la requête et injecte client/profil dans g.
    La clé peut être transmise via :
      • header  X-API-Key: <clé>
      • param   ?api_key=<clé>
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        raw_key = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
        )

        db = next(get_db())
        client, api_key = resolve_api_key(raw_key, db)

        if not client:
            _log_audit(db, None, "auth_failed", None, 401,
                       f"IP={_pseudo_ip(request.remote_addr)}")
            logger.warning("Auth échouée | IP=%s path=%s", request.remote_addr, request.path)
            return jsonify({"error": "Clé API invalide ou absente."}), 401

        # Injection dans le contexte de la requête
        g.client    = client
        g.api_key   = api_key
        g.db        = db
        g.key_hint  = api_key.hint

        return f(*args, **kwargs)

    return decorated


def require_profile(*profiles):
    """
    Décorateur — restreint l'accès à certains profils.
    Doit être utilisé APRÈS @require_api_key.
    Ex: @require_profile("admin", "analyste")
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "client"):
                return jsonify({"error": "Non authentifié."}), 401
            if g.client.profil not in profiles:
                return jsonify({
                    "error": f"Accès refusé. Profil requis : {profiles}. "
                             f"Votre profil : {g.client.profil}"
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Logging RGPD ────────────────────────────────────────────────────────────

def _pseudo_ip(ip: str | None) -> str:
    """Pseudonymise l'IP : ne conserve que le /24 (IPv4) ou /48 (IPv6)."""
    if not ip:
        return "unknown"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return ip[:ip.rfind(":") + 1] + "xxx" if ":" in ip else ip


def _log_audit(
    db: Session,
    client_id: str | None,
    action: str,
    resource_id: str | None,
    status_code: int,
    detail: str | None = None,
):
    try:
        log = AuditLog(
            client_id   = client_id,
            ip_address  = _pseudo_ip(request.remote_addr),
            action      = action,
            resource_id = resource_id,
            status_code = status_code,
            detail      = detail,
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.error("Échec écriture audit_log : %s", exc)
        db.rollback()


def log_audit(action: str, resource_id: str | None = None,
              status_code: int = 200, detail: str | None = None):
    """Raccourci à appeler depuis une route (g.client doit être présent)."""
    db = getattr(g, "db", next(get_db()))
    client_id = g.client.id if hasattr(g, "client") else None
    _log_audit(db, client_id, action, resource_id, status_code, detail)


# ── Middleware de métriques ──────────────────────────────────────────────────

def record_metric(route: str, method: str, status_code: int,
                  duration_ms: float, client_hint: str | None = None):
    """Enregistre une métrique de performance. Non bloquant."""
    db = next(get_db())
    try:
        m = RequestMetric(
            route       = route,
            method      = method,
            status_code = status_code,
            duration_ms = duration_ms,
            client_hint = client_hint,
        )
        db.add(m)
        db.commit()
    except Exception as exc:
        logger.error("Échec écriture metric : %s", exc)
        db.rollback()
    finally:
        db.close()

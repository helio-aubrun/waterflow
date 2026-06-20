"""
api/models/db.py — Modèles SQLAlchemy conformes RGPD

Tables :
  - clients        : entités collectivités (pseudonymisées)
  - prelevements   : fiches de prélèvement brutes
  - mesures        : valeurs physico-chimiques normalisées
  - predictions    : résultats du modèle ML
  - api_keys       : clés API hashées par client
  - audit_logs     : journal d'accès RGPD
  - request_metrics: métriques de performance par route
"""

import os
import uuid
import hashlib
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, String, Float, Integer,
    Boolean, DateTime, Text, ForeignKey, Index, Enum
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
import enum

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///waterflow2.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Base ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Enums ───────────────────────────────────────────────────────────────────

class ProfileEnum(str, enum.Enum):
    ADMIN    = "admin"
    ANALYSTE = "analyste"
    TERRAIN  = "terrain"
    READONLY = "readonly"


class IngestionSourceEnum(str, enum.Enum):
    MANUAL = "manual"
    OCR    = "ocr"
    API    = "api"


# ── Tables ──────────────────────────────────────────────────────────────────

class Client(Base):
    """
    Collectivité ou agent déposant des prélèvements.
    RGPD : nom stocké pseudonymisé, email hashé.
    """
    __tablename__ = "clients"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code           = Column(String(64), unique=True, nullable=False, index=True)  # ex: COMM-042
    nom_pseudo     = Column(String(128), nullable=True)       # pseudonyme libre
    email_hash     = Column(String(64),  nullable=True)       # SHA-256 de l'email
    profil         = Column(Enum(ProfileEnum), default=ProfileEnum.TERRAIN)
    actif          = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=utcnow)
    rgpd_consent   = Column(Boolean, default=False)           # consentement RGPD explicite
    rgpd_consent_at= Column(DateTime, nullable=True)
    anonymised_at  = Column(DateTime, nullable=True)          # date d'anonymisation RGPD

    api_keys       = relationship("ApiKey",      back_populates="client", cascade="all, delete-orphan")
    prelevements   = relationship("Prelevement", back_populates="client")

    @staticmethod
    def hash_email(email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class ApiKey(Base):
    """
    Clés API par client — stockées hashées, jamais en clair.
    """
    __tablename__ = "api_keys"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    key_hash   = Column(String(64), unique=True, nullable=False, index=True)
    hint       = Column(String(8),  nullable=False)   # 4 premiers chars pour identification
    label      = Column(String(64), nullable=True)    # ex: "mobile-terrain-A"
    actif      = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used  = Column(DateTime, nullable=True)

    client     = relationship("Client", back_populates="api_keys")

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()


class Prelevement(Base):
    """
    Fiche de prélèvement brute.
    Liaison 1-N vers Mesure et Prediction.
    """
    __tablename__ = "prelevements"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id       = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    date_prelevement= Column(DateTime, nullable=True)
    lieu            = Column(String(256), nullable=True)
    source          = Column(Enum(IngestionSourceEnum), default=IngestionSourceEnum.API)
    fichier_nom     = Column(String(256), nullable=True)   # nom du fichier original
    fichier_type    = Column(String(64),  nullable=True)   # MIME type
    ocr_raw_text    = Column(Text, nullable=True)          # transcription brute OCR
    ocr_warnings    = Column(Text, nullable=True)          # JSON array de warnings
    observations    = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=utcnow)

    client          = relationship("Client",     back_populates="prelevements")
    mesures         = relationship("Mesure",     back_populates="prelevement", uselist=False,
                                   cascade="all, delete-orphan")
    predictions     = relationship("Prediction", back_populates="prelevement",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_prev_client_date", "client_id", "date_prelevement"),
    )


class Mesure(Base):
    """
    Valeurs physico-chimiques normalisées d'un prélèvement.
    """
    __tablename__ = "mesures"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prelevement_id   = Column(String(36), ForeignKey("prelevements.id", ondelete="CASCADE"),
                               nullable=False, unique=True, index=True)
    ph               = Column(Float, nullable=True)
    hardness         = Column(Float, nullable=True)
    solids           = Column(Float, nullable=True)
    chloramines      = Column(Float, nullable=True)
    sulfate          = Column(Float, nullable=True)
    conductivity     = Column(Float, nullable=True)
    organic_carbon   = Column(Float, nullable=True)
    trihalomethanes  = Column(Float, nullable=True)
    turbidity        = Column(Float, nullable=True)

    prelevement      = relationship("Prelevement", back_populates="mesures")

    def to_feature_dict(self) -> dict:
        return {
            "ph":              self.ph,
            "Hardness":        self.hardness,
            "Solids":          self.solids,
            "Chloramines":     self.chloramines,
            "Sulfate":         self.sulfate,
            "Conductivity":    self.conductivity,
            "Organic_carbon":  self.organic_carbon,
            "Trihalomethanes": self.trihalomethanes,
            "Turbidity":       self.turbidity,
        }


class Prediction(Base):
    """
    Résultat du modèle ML pour un prélèvement.
    Conserve la version du modèle pour traçabilité.
    """
    __tablename__ = "predictions"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prelevement_id = Column(String(36), ForeignKey("prelevements.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    potable        = Column(Integer,  nullable=False)      # 0 ou 1
    probability    = Column(Float,    nullable=False)
    model_version  = Column(String(64), nullable=True)     # ex: "WaterQualityXGBoost/1"
    created_at     = Column(DateTime, default=utcnow)

    prelevement    = relationship("Prelevement", back_populates="predictions")


class AuditLog(Base):
    """
    Journal d'accès RGPD — immuable.
    Enregistre toutes les opérations sensibles sur les données.
    """
    __tablename__ = "audit_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp   = Column(DateTime, default=utcnow, index=True)
    client_id   = Column(String(36), nullable=True, index=True)  # peut être null si clé inconnue
    ip_address  = Column(String(45), nullable=True)              # IPv4 ou IPv6 (pseudonymisée)
    action      = Column(String(64), nullable=False)             # ex: "predict", "ocr", "read_data"
    resource_id = Column(String(36), nullable=True)              # ID de la ressource accédée
    status_code = Column(Integer, nullable=True)
    detail      = Column(Text, nullable=True)


class RequestMetric(Base):
    """
    Métriques de performance par requête — pour monitoring responsable exploitation.
    Agrégées périodiquement, les lignes brutes peuvent être purgées.
    """
    __tablename__ = "request_metrics"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp    = Column(DateTime, default=utcnow, index=True)
    route        = Column(String(128), nullable=False, index=True)
    method       = Column(String(8),   nullable=False)
    status_code  = Column(Integer,     nullable=False)
    duration_ms  = Column(Float,       nullable=False)
    client_hint  = Column(String(8),   nullable=True)   # 4 chars de la clé pour regroupement


def init_db():
    """Crée toutes les tables si elles n'existent pas."""
    Base.metadata.create_all(bind=engine)

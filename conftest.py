"""
conftest.py — configuration pytest
"""
import os

# Set all test environment variables before any test module is imported.
# Combined tokens cover all test files: test_api.py (alice, bob) + test_e2e.py (admin).
os.environ.setdefault("DATABASE_URL",      "sqlite:///:memory:")
os.environ.setdefault("SCALER_PATH",       "mock")
os.environ.setdefault("OCR_SPACE_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault(
    "EXPERT_TOKENS",
    "alice:token-alice:analyste,bob:token-bob:exploit,admin:token-admin-e2e:exploit",
)

# ─────────────────────────────────────────────────────────────────────────────
# Correctif incident #1 (cf. docs/incident.md) :
# tests/test_non_regression.py::TestMetriquesPerformance dépend de
# data/water_potability_clean.csv, un fichier dérivé volontairement
# gitignoré ("régénéré par le notebook d'EDA"). Sur un clone frais du dépôt,
# ce fichier est absent et fait échouer 3 tests avec un FileNotFoundError.
#
# Ce fixture de session régénère le fichier manquant en reproduisant
# exactement le pipeline de nettoyage du notebook water_potability_eda.ipynb
# (suppression des doublons, imputation par médiane conditionnelle,
# winsorisation 1%-99%), rendant la suite de tests autonome vis-à-vis du
# notebook tout en produisant un résultat identique.
# ─────────────────────────────────────────────────────────────────────────────
import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_clean_dataset():
    root       = os.path.dirname(__file__)
    raw_path   = os.path.join(root, "data", "water_potability.csv")
    clean_path = os.path.join(root, "data", "water_potability_clean.csv")

    if os.path.exists(clean_path) or not os.path.exists(raw_path):
        return  # rien à faire : deja present, ou pas de source pour regenerer

    import pandas as pd
    from scipy.stats.mstats import winsorize

    df = pd.read_csv(raw_path).drop_duplicates()

    features     = [c for c in df.columns if c != "Potability"]
    missing_cols = ["ph", "Sulfate", "Trihalomethanes"]

    for col in missing_cols:
        medians       = df.groupby("Potability")[col].transform("median")
        global_median = df[col].median()
        df[col] = df[col].fillna(medians).fillna(global_median)

    df[features] = df[features].apply(
        lambda col: pd.Series(winsorize(col, limits=[0.01, 0.01]), index=col.index)
    )

    df.to_csv(clean_path, index=False)


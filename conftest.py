"""
conftest.py — configuration pytest
"""
import os

# Set all test environment variables before any test module is imported.
# Combined tokens cover all test files: test_api.py (alice, bob) + test_e2e.py (admin).
os.environ.setdefault("DATABASE_URL",      "sqlite:///:memory:")
os.environ.setdefault("MLFLOW_URI",        "mock")
os.environ.setdefault("SCALER_PATH",       "mock")
os.environ.setdefault("OCR_SPACE_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault(
    "EXPERT_TOKENS",
    "alice:token-alice:analyste,bob:token-bob:exploit,admin:token-admin-e2e:exploit",
)

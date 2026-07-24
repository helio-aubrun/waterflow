"""
main.py — Point d'entrée Waterflow 2
Lance le serveur Flask ou Gunicorn selon l'environnement.
"""

import os
from dotenv import load_dotenv
load_dotenv()  # charge .env si présent

from api.app import create_app  # noqa: E402 — après load_dotenv(), volontaire

app = create_app()

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)

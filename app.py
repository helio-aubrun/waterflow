"""
api/app.py — Factory Flask Waterflow 2
"""

import logging
from flask import Flask
from api.models.db    import init_db
from api.routes.routes import bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../frontend/templates",
        static_folder="../frontend/static",
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    # Initialise les tables si elles n'existent pas
    init_db()

    app.register_blueprint(bp)

    return app

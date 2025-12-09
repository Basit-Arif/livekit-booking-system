import os
from flask import Flask

from extensions import db, migrate
from config import DevConfig, ProdConfig


def create_app() -> Flask:
    """Initialize Flask app with DB + configuration."""
    app = Flask(__name__)

    if os.getenv("FLASK_ENV") == "production":
        app.config.from_object(ProdConfig)
    else:
        app.config.from_object(DevConfig)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so SQLAlchemy registers tables.
    with app.app_context():
        from src.models.patient_db import Patient  # noqa: F401
        from src.models.appointments_db import Appointment  # noqa: F401
        # Ensure tables exist (useful for SQLite/dev). For production, prefer migrations.
        db.create_all()

        # Register HTTP blueprints
        from src.routes.dashboard import dashboard_bp

        app.register_blueprint(dashboard_bp)

    return app

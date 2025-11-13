from contextlib import contextmanager
from src.app_factory import create_app

# Create your Flask app instance once
flask_app = create_app()

@contextmanager
def db_context():
    """Provide a transactional scope around a series of DB operations."""
    with flask_app.app_context():
        yield
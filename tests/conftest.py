"""Configuración común de las pruebas."""

import sys
from pathlib import Path

import pytest

# Permite importar el paquete app/ al ejecutar pytest desde la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    """App aislada con SQLite temporal y scheduler desactivado."""

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "clave-de-pruebas"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        SCHEDULER_ENABLED = False
        DEFAULT_URLS = ""
        NTFY_TOPIC = ""
        EMAIL_TO = ""
        SMTP_HOST = ""
        SMTP_USER = ""
        SMTP_PASSWORD = ""
        TELEGRAM_BOT_TOKEN = ""
        TELEGRAM_CHAT_ID = ""
        REQUEST_DELAY_SECONDS = 0
        MAX_PRODUCT_PAGES = 0

    aplicacion = create_app(TestConfig)
    yield aplicacion

    from app.extensions import db

    with aplicacion.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Cliente de pruebas de Flask."""
    return app.test_client()

"""Instancias compartidas de extensiones."""

from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# El scheduler se arranca en create_app() y se evita duplicarlo con el reloader.
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

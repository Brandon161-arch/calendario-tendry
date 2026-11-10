"""Punto de entrada para ejecutar la aplicación en local."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# Registro en archivo: útil cuando se ejecuta con pythonw (sin consola).
_handlers = [
    RotatingFileHandler(
        INSTANCE_DIR / "app.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
]
if sys.stderr is not None:
    _handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=_handlers,
)

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "si", "on"},
    )

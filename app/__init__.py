"""Fábrica de la aplicación Flask."""

from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template

from .config import Config
from .extensions import db
from .utils import token_csrf, validar_csrf


def _hora_local(valor, formato: str = "%d/%m/%Y %H:%M") -> str:
    """Convierte un datetime UTC naive a la hora local del sistema."""
    if not valor:
        return "—"
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone().strftime(formato)


def _hace(valor) -> str:
    """Devuelve un texto tipo 'hace 3 min' para una fecha pasada."""
    if not valor:
        return "sin revisiones"
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    segundos = (datetime.now(timezone.utc) - valor).total_seconds()
    if segundos < 0:
        return "ahora mismo"
    if segundos < 60:
        return "hace unos segundos"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"hace {minutos} min"
    horas = int(segundos // 3600)
    if horas < 24:
        return f"hace {horas} h"
    dias = int(segundos // 86400)
    return f"hace {dias} día{'s' if dias != 1 else ''}"


def _faltan(valor) -> str:
    """Devuelve un texto tipo 'en 12 min' para una fecha futura."""
    if not valor:
        return "sin programar"
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    segundos = (valor - datetime.now(timezone.utc)).total_seconds()
    if segundos <= 0:
        return "ahora mismo"
    if segundos < 60:
        return "en unos segundos"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"en {minutos} min"
    horas = int(segundos // 3600)
    if horas < 24:
        return f"en {horas} h"
    dias = int(horas // 24)
    return f"en {dias} día{'s' if dias != 1 else ''}"


def create_app(config_class=Config) -> Flask:
    """Crea y configura la aplicación, la base de datos y el scheduler."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from .models import inicializar_datos

    with app.app_context():
        db.create_all()
        inicializar_datos(app)

    from .routes import bp

    app.register_blueprint(bp)

    app.before_request(validar_csrf)
    app.jinja_env.globals["csrf_token"] = token_csrf
    app.jinja_env.filters["localtime"] = _hora_local
    app.jinja_env.filters["hace"] = _hace
    app.jinja_env.filters["faltan"] = _faltan

    @app.errorhandler(404)
    def no_encontrada(error):  # noqa: ARG001
        return render_template("404.html"), 404

    from .scheduler import iniciar_scheduler

    iniciar_scheduler(app)

    return app

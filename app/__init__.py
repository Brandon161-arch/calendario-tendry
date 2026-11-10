"""Fábrica de la aplicación Flask."""

from datetime import timezone
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

    @app.errorhandler(404)
    def no_encontrada(error):  # noqa: ARG001
        return render_template("404.html"), 404

    from .scheduler import iniciar_scheduler

    iniciar_scheduler(app)

    return app

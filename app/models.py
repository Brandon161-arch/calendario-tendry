"""Modelos de datos y datos iniciales."""

import re
from datetime import datetime, timezone

from .extensions import db
from .utils import parsear_keywords, parsear_urls


def utcnow() -> datetime:
    """Fecha/hora UTC sin zona (SQLite guarda datetimes naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Setting(db.Model):
    """Configuración editable desde la web, en formato clave/valor."""

    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        fila = db.session.get(cls, key)
        return fila.value if fila is not None else default

    @classmethod
    def set(cls, key: str, value: str) -> None:
        fila = db.session.get(cls, key)
        if fila is None:
            db.session.add(cls(key=key, value=str(value)))
        else:
            fila.value = str(value)

    @classmethod
    def get_list(cls, key: str) -> list[str]:
        """Lista separada por líneas o comas."""
        bruto = cls.get(key, "") or ""
        return [parte.strip() for parte in re.split(r"[\n,]+", bruto) if parte.strip()]

    @classmethod
    def get_int(cls, key: str, default: int) -> int:
        try:
            return int(cls.get(key, "") or default)
        except (TypeError, ValueError):
            return default


class TargetURL(db.Model):
    """Cada página del sitio que se revisa periódicamente."""

    __tablename__ = "target_urls"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False, default="")
    url = db.Column(db.String(1024), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_checked_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(32))
    last_http_status = db.Column(db.Integer)
    last_error = db.Column(db.Text)


class CheckLog(db.Model):
    """Historial de cada revisión realizada a una URL."""

    __tablename__ = "check_logs"

    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey("target_urls.id"), nullable=True)
    url = db.Column(db.String(1024), nullable=False)
    checked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    result = db.Column(db.String(32), nullable=False, default="not_found")
    http_status = db.Column(db.Integer)
    error = db.Column(db.Text)
    matched_term = db.Column(db.String(255))
    matched_link = db.Column(db.String(1024))


class Detection(db.Model):
    """Hallazgo único; se notifica una sola vez hasta reiniciar la alerta."""

    __tablename__ = "detections"

    id = db.Column(db.Integer, primary_key=True)
    dedupe_key = db.Column(db.String(512), nullable=False, unique=True)
    kind = db.Column(db.String(32), nullable=False, default="keyword")
    url = db.Column(db.String(1024), nullable=False)
    matched_term = db.Column(db.String(255))
    link = db.Column(db.String(1024))
    snippet = db.Column(db.Text)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    notified_at = db.Column(db.DateTime)


class ProductState(db.Model):
    """Estado de disponibilidad de un producto para detectar transiciones."""

    __tablename__ = "product_states"

    id = db.Column(db.Integer, primary_key=True)
    product_key = db.Column(db.String(512), nullable=False, unique=True)
    url = db.Column(db.String(1024), nullable=False)
    name = db.Column(db.String(255), nullable=False, default="")
    availability = db.Column(db.String(16), nullable=False, default="unknown")
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class BotState(db.Model):
    """Estado global del bot (fila única con id=1)."""

    __tablename__ = "bot_state"

    id = db.Column(db.Integer, primary_key=True, default=1)
    running = db.Column(db.Boolean, nullable=False, default=True)
    calendar_found = db.Column(db.Boolean, nullable=False, default=False)
    last_check_at = db.Column(db.DateTime)
    next_check_at = db.Column(db.DateTime)
    last_result = db.Column(db.String(32), nullable=False, default="never")
    last_error = db.Column(db.Text)
    last_match_url = db.Column(db.String(1024))
    last_match_term = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @classmethod
    def get(cls) -> "BotState":
        estado = db.session.get(cls, 1)
        if estado is None:
            estado = cls(id=1)
            db.session.add(estado)
            db.session.commit()
        return estado


def sembrar_urls_iniciales(app) -> int:
    """Activa las URLs por defecto cuando no hay ninguna URL activa."""
    urls_iniciales = parsear_urls(app.config.get("DEFAULT_URLS") or "")
    if not urls_iniciales:
        return 0
    if TargetURL.query.filter_by(active=True).count() > 0:
        return 0

    existentes = {
        objetivo.url.rstrip("/"): objetivo for objetivo in TargetURL.query.all()
    }
    activadas = 0
    for etiqueta, url in urls_iniciales:
        clave = url.rstrip("/")
        objetivo = existentes.get(clave)
        if objetivo is None:
            db.session.add(TargetURL(label=etiqueta, url=url, active=True))
        else:
            objetivo.active = True
            if not objetivo.label:
                objetivo.label = etiqueta
        activadas += 1

    if not Setting.get("store_url") and app.config.get("STORE_URL"):
        Setting.set("store_url", app.config["STORE_URL"])

    db.session.commit()
    if activadas:
        app.logger.info("URLs iniciales activadas: %s", activadas)
    return activadas


def inicializar_datos(app) -> None:
    """Crea la configuración inicial y el estado del bot si no existen."""
    valores = {
        "interval_minutes": str(app.config["CHECK_INTERVAL_MINUTES"]),
        "keywords": app.config["DEFAULT_KEYWORDS"],
        "notify_channel": app.config["NOTIFY_CHANNEL"],
        "ntfy_server": app.config["NTFY_SERVER"],
        "ntfy_topic": app.config["NTFY_TOPIC"],
        "email_to": app.config["EMAIL_TO"],
        "whatsapp_to": app.config["WHATSAPP_TO"],
        "telegram_chat_id": app.config["TELEGRAM_CHAT_ID"],
        "store_url": app.config["STORE_URL"],
    }
    for clave, valor in valores.items():
        if db.session.get(Setting, clave) is None:
            db.session.add(Setting(key=clave, value=valor or ""))

    if db.session.get(BotState, 1) is None:
        db.session.add(BotState(id=1, running=True, calendar_found=False, last_result="never"))

    # Si no hay ninguna URL activa (primer arranque, despliegue nuevo o una
    # base que quedó vacía), se activan las URLs oficiales por defecto.
    sembrar_urls_iniciales(app)

    # Normaliza palabras clave mal guardadas.
    if db.session.get(Setting, "keywords") is not None:
        actual = Setting.get_list("keywords")
        Setting.set("keywords", "\n".join(parsear_keywords("\n".join(actual))))

    db.session.commit()

"""Configuración de la aplicación a partir de variables de entorno."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Raíz del proyecto (un nivel por encima de app/)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(nombre: str, por_defecto: bool = False) -> bool:
    """Lee un booleano aceptando valores habituales (1, true, si, on...)."""
    valor = os.getenv(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _env_int(nombre: str, por_defecto: int) -> int:
    """Lee un entero sin romper la app si el valor no es válido."""
    try:
        return int(os.getenv(nombre, str(por_defecto)))
    except (TypeError, ValueError):
        return por_defecto


def _env_float(nombre: str, por_defecto: float) -> float:
    """Lee un decimal sin romper la app si el valor no es válido."""
    try:
        return float(os.getenv(nombre, str(por_defecto)))
    except (TypeError, ValueError):
        return por_defecto


def _url_base_datos() -> str:
    """Devuelve la URL de SQLAlchemy, normalizando la que dan algunos PaaS."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        # SQLAlchemy 2 exige el esquema postgresql://
        url = url.replace("postgres://", "postgresql://", 1)
    if url:
        return url
    ruta = (BASE_DIR / "instance" / "tendry.db").as_posix()
    return f"sqlite:///{ruta}"


class Config:
    """Valores por defecto; se pueden sobrescribir desde .env."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    SQLALCHEMY_DATABASE_URI = _url_base_datos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Rastreo
    CHECK_INTERVAL_MINUTES = _env_int("CHECK_INTERVAL_MINUTES", 15)
    REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 20)
    REQUEST_DELAY_SECONDS = _env_float("REQUEST_DELAY_SECONDS", 2.0)
    MAX_PRODUCT_PAGES = _env_int("MAX_PRODUCT_PAGES", 5)
    USER_AGENT = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )

    # Tienda que se muestra al final del panel
    STORE_URL = os.getenv("STORE_URL", "https://www.maquillajetrendyshop.com/")

    # Valores iniciales de la configuración editable
    DEFAULT_URLS = os.getenv(
        "DEFAULT_URLS",
        "Tienda Trendy | https://www.maquillajetrendyshop.com/, "
        "Calendario de Adviento | https://www.maquillajetrendyshop.com/calendario-de-adviento",
    )
    DEFAULT_KEYWORDS = os.getenv(
        "DEFAULT_KEYWORDS",
        "calendario de adviento, advent calendar, adviento",
    )

    # Notificaciones
    NOTIFY_CHANNEL = os.getenv("NOTIFY_CHANNEL", "ntfy")
    NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
    EMAIL_TO = os.getenv("EMAIL_TO", "")

    # SMTP (solo desde .env por seguridad)
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _env_int("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)

    # WhatsApp (credenciales solo desde .env; el número se edita en la web)
    WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "").strip().lower()
    WHATSAPP_TO = os.getenv("WHATSAPP_TO", "")
    CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # Telegram (token solo desde .env)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Scheduler
    SCHEDULER_ENABLED = _env_bool("SCHEDULER_ENABLED", True)

    # Confiar en las cabeceras X-Forwarded-* del proxy (Coolify/Traefik)
    TRUST_PROXY = _env_bool("TRUST_PROXY", False)

    # Servidor local
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 5000)
    DEBUG = _env_bool("FLASK_DEBUG", True)

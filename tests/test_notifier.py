"""Pruebas del envío de notificaciones (sin red real)."""

from app import notifier


class RespuestaFalsa:
    status_code = 200
    text = "ok"


class SMTPFalso:
    enviados = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, usuario, clave):
        pass

    def send_message(self, mensaje):
        SMTPFalso.enviados.append(mensaje)


def test_ntfy_envia_tema_y_enlace(monkeypatch):
    capturado = {}

    def post_falso(url, data=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["data"] = data
        capturado["headers"] = headers
        return RespuestaFalsa()

    monkeypatch.setattr(notifier.requests, "post", post_falso)

    ok, _ = notifier.enviar_ntfy(
        "https://ntfy.sh",
        "tema-de-prueba",
        "Aviso",
        "Hola",
        "https://tendry.test/calendario",
    )

    assert ok
    assert capturado["url"] == "https://ntfy.sh/tema-de-prueba"
    assert capturado["data"] == b"Hola"
    assert capturado["headers"]["Click"] == "https://tendry.test/calendario"


def test_ntfy_sin_tema_falla():
    ok, detalle = notifier.enviar_ntfy("https://ntfy.sh", "", "Aviso", "Hola", None)
    assert not ok
    assert "tema" in detalle.lower()


def test_email_sin_configuracion_falla(app):
    with app.app_context():
        ok, detalle = notifier.enviar_email(app, "destino@example.com", "Asunto", "Cuerpo")
    assert not ok
    assert "SMTP" in detalle


def test_email_envia_texto_y_html_con_enlace(app, monkeypatch):
    app.config.update(
        SMTP_HOST="smtp.test",
        SMTP_PORT=587,
        SMTP_USER="origen@test.com",
        SMTP_PASSWORD="clave",
        SMTP_FROM="origen@test.com",
        SMTP_USE_TLS=True,
        SMTP_USE_SSL=False,
    )
    SMTPFalso.enviados.clear()
    monkeypatch.setattr(notifier.smtplib, "SMTP", SMTPFalso)

    ok, _ = notifier.enviar_email(
        app,
        "destino@test.com",
        "Calendario disponible",
        "Hola",
        "https://tendry.test/calendario",
    )

    assert ok
    mensaje = SMTPFalso.enviados[0]
    assert mensaje["To"] == "destino@test.com"
    tipos = {parte.get_content_type() for parte in mensaje.walk()}
    assert "text/plain" in tipos
    assert "text/html" in tipos
    parte_html = next(
        parte for parte in mensaje.walk() if parte.get_content_type() == "text/html"
    )
    assert "https://tendry.test/calendario" in parte_html.get_content()


def test_whatsapp_sin_configuracion_falla(app):
    app.config.update(
        WHATSAPP_PROVIDER="",
        CALLMEBOT_APIKEY="",
        TWILIO_ACCOUNT_SID="",
        TWILIO_AUTH_TOKEN="",
        TWILIO_WHATSAPP_FROM="",
    )
    ok, detalle = notifier.enviar_whatsapp(app, "+34600111222", "Hola")
    assert not ok
    assert "WhatsApp" in detalle


def test_whatsapp_callmebot_envia_mensaje(app, monkeypatch):
    app.config.update(
        WHATSAPP_PROVIDER="callmebot",
        CALLMEBOT_APIKEY="clave123",
        WHATSAPP_TO="+34600111222",
    )
    capturado = {}

    def get_falso(url, params=None, timeout=None):
        capturado["url"] = url
        capturado["params"] = params
        return RespuestaFalsa()

    monkeypatch.setattr(notifier.requests, "get", get_falso)

    ok, _ = notifier.enviar_whatsapp(
        app,
        "+34600111222",
        "Hola",
        "https://tendry.test/calendario",
    )

    assert ok
    assert capturado["url"] == "https://api.callmebot.com/whatsapp.php"
    assert capturado["params"]["phone"] == "+34600111222"
    assert capturado["params"]["apikey"] == "clave123"
    assert "https://tendry.test/calendario" in capturado["params"]["text"]


def test_whatsapp_twilio_envia_mensaje(app, monkeypatch):
    app.config.update(
        WHATSAPP_PROVIDER="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_WHATSAPP_FROM="whatsapp:+14155238886",
    )
    capturado = {}

    def post_falso(url, auth=None, data=None, timeout=None):
        capturado["url"] = url
        capturado["auth"] = auth
        capturado["data"] = data
        return RespuestaFalsa()

    monkeypatch.setattr(notifier.requests, "post", post_falso)

    ok, _ = notifier.enviar_whatsapp(
        app,
        "+34600111222",
        "Hola",
        "https://tendry.test/calendario",
    )

    assert ok
    assert capturado["auth"] == ("AC123", "token")
    assert capturado["data"]["From"] == "whatsapp:+14155238886"
    assert capturado["data"]["To"] == "whatsapp:+34600111222"
    assert "https://tendry.test/calendario" in capturado["data"]["Body"]


def test_telegram_sin_token_falla(app):
    with app.app_context():
        ok, detalle = notifier.enviar_telegram(app, "123456", "Hola")
    assert not ok
    assert "TOKEN" in detalle

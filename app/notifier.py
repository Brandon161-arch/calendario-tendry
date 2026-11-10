"""Envío de notificaciones por ntfy, correo SMTP, WhatsApp y Telegram."""

import html
import smtplib
import unicodedata
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib.parse import quote

import requests

from .models import Setting


def _texto_ascii(texto: str) -> str:
    """Convierte a ASCII para cabeceras HTTP (ntfy) sin romper el envío."""
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).encode(
        "ascii", "ignore"
    ).decode("ascii")


def _normalizar_telefono(telefono: str) -> str:
    """Deja el número en formato +NNNNNNNN, sin espacios ni guiones."""
    limpio = "".join(c for c in (telefono or "").strip() if c.isdigit() or c == "+")
    if not limpio:
        return ""
    return "+" + limpio.lstrip("+")


def _cuerpo_html(asunto: str, mensaje: str, enlace: str | None) -> str:
    """Construye un correo HTML sencillo y elegante con el enlace destacado."""
    parrafos = "".join(
        '<p style="margin:0 0 12px;font-size:15px;line-height:1.65;color:#5c4650;">'
        f"{html.escape(linea)}</p>"
        for linea in mensaje.splitlines()
        if linea.strip()
    )
    boton = ""
    if enlace:
        boton = (
            '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:22px 0 6px;">'
            '<tr><td style="border-radius:999px;background:#a84768;">'
            f'<a href="{html.escape(enlace, quote=True)}" style="display:inline-block;'
            "padding:13px 24px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;"
            'color:#ffffff;text-decoration:none;">Abrir el calendario</a>'
            "</td></tr></table>"
        )
    return f"""<!doctype html>
<html lang="es">
<body style="margin:0;padding:0;background:#fbf6f2;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fbf6f2;padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
        style="max-width:560px;background:#fffdfb;border:1px solid #eedfdd;border-radius:24px;overflow:hidden;">
        <tr><td style="padding:34px 34px 8px;text-align:center;">
          <div style="width:46px;height:46px;line-height:46px;border-radius:50%;background:#a84768;
            color:#ffffff;font-family:Georgia,serif;font-size:22px;margin:0 auto 12px;">T</div>
          <p style="margin:0;font-family:Arial,sans-serif;font-size:10px;letter-spacing:3px;
            text-transform:uppercase;color:#a84768;font-weight:bold;">Tendry · Advent tracker</p>
          <h1 style="margin:10px 0 18px;font-family:Georgia,serif;font-size:27px;line-height:1.2;
            font-weight:normal;color:#37222c;">{html.escape(asunto)}</h1>
        </td></tr>
        <tr><td style="padding:0 34px 30px;">
          {parrafos}
          {boton}
          <p style="margin:26px 0 0;padding-top:18px;border-top:1px solid #eedfdd;
            font-family:Arial,sans-serif;font-size:12px;line-height:1.6;color:#8d7480;">
            Recibes este aviso porque activaste las notificaciones por correo en tu rastreador de Tendry.
            Solo se envía una vez por hallazgo.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def enviar_ntfy(servidor: str, tema: str, asunto: str, mensaje: str, enlace: str | None) -> tuple[bool, str]:
    """Publica en ntfy.sh. El título va en ASCII y el cuerpo en UTF-8."""
    if not tema:
        return False, "Falta el tema (topic) de ntfy."
    servidor = (servidor or "https://ntfy.sh").rstrip("/")
    cabeceras = {
        "Title": _texto_ascii(asunto),
        "Priority": "high",
        "Tags": "tada,warning",
    }
    if enlace:
        cabeceras["Click"] = quote(enlace, safe=":/?&=#%+")
    try:
        respuesta = requests.post(
            f"{servidor}/{tema}",
            data=mensaje.encode("utf-8"),
            headers=cabeceras,
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"Error de conexión con ntfy: {exc}"
    if respuesta.status_code >= 400:
        return False, f"ntfy respondió HTTP {respuesta.status_code}: {respuesta.text[:200]}"
    return True, "Notificación ntfy enviada."


def enviar_email(
    app,
    destinatario: str,
    asunto: str,
    mensaje: str,
    enlace: str | None = None,
) -> tuple[bool, str]:
    """Envía un correo con versión de texto y versión HTML."""
    cfg = app.config
    if not destinatario:
        return False, "Falta el correo destinatario."
    if not (cfg.get("SMTP_HOST") and cfg.get("SMTP_USER") and cfg.get("SMTP_PASSWORD")):
        return False, "Faltan SMTP_HOST, SMTP_USER o SMTP_PASSWORD en .env."

    texto = mensaje if not enlace else f"{mensaje}\n\nEnlace: {enlace}"

    correo = EmailMessage()
    correo["From"] = cfg.get("SMTP_FROM") or cfg["SMTP_USER"]
    correo["To"] = destinatario
    correo["Subject"] = asunto
    correo["Date"] = formatdate(localtime=True)
    correo["Message-ID"] = make_msgid()
    correo.set_content(texto)
    correo.add_alternative(_cuerpo_html(asunto, mensaje, enlace), subtype="html")

    try:
        if cfg.get("SMTP_USE_SSL"):
            with smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=20) as servidor:
                servidor.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                servidor.send_message(correo)
        else:
            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=20) as servidor:
                servidor.ehlo()
                if cfg.get("SMTP_USE_TLS"):
                    servidor.starttls()
                    servidor.ehlo()
                servidor.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                servidor.send_message(correo)
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"Error SMTP: {exc}"
    return True, "Correo enviado."


def _whatsapp_callmebot(apikey: str, destino: str, texto: str) -> tuple[bool, str]:
    """Envío gratuito con CallMeBot (uso personal, API no oficial)."""
    telefono = _normalizar_telefono(destino)
    if not telefono:
        return False, "Falta el número de WhatsApp de destino."
    try:
        respuesta = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": telefono, "text": texto, "apikey": apikey},
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, f"Error de conexión con CallMeBot: {exc}"

    cuerpo = (respuesta.text or "")[:300]
    if respuesta.status_code >= 400 or "error" in cuerpo.lower():
        return False, f"CallMeBot respondió: {cuerpo or respuesta.status_code}"
    return True, "WhatsApp enviado con CallMeBot."


def _whatsapp_twilio(
    sid: str,
    token: str,
    remitente: str,
    destino: str,
    texto: str,
) -> tuple[bool, str]:
    """Envío con la API oficial de Twilio (WhatsApp Sandbox o número propio)."""
    telefono = _normalizar_telefono(destino)
    if not telefono:
        return False, "Falta el número de WhatsApp de destino."
    desde = remitente if remitente.startswith("whatsapp:") else f"whatsapp:{_normalizar_telefono(remitente)}"
    hacia = telefono if telefono.startswith("whatsapp:") else f"whatsapp:{telefono}"

    try:
        respuesta = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"From": desde, "To": hacia, "Body": texto},
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, f"Error de conexión con Twilio: {exc}"

    if respuesta.status_code >= 400:
        try:
            detalle = respuesta.json().get("message", respuesta.text[:200])
        except ValueError:
            detalle = respuesta.text[:200]
        return False, f"Twilio respondió HTTP {respuesta.status_code}: {detalle}"
    return True, "WhatsApp enviado con Twilio."


def enviar_whatsapp(
    app,
    destino: str,
    mensaje: str,
    enlace: str | None = None,
) -> tuple[bool, str]:
    """Envía un WhatsApp usando Twilio o CallMeBot según la configuración."""
    texto = mensaje if not enlace else f"{mensaje}\n\nEnlace: {enlace}"
    cfg = app.config
    apikey = cfg.get("CALLMEBOT_APIKEY")
    sid = cfg.get("TWILIO_ACCOUNT_SID")
    token = cfg.get("TWILIO_AUTH_TOKEN")
    remitente = cfg.get("TWILIO_WHATSAPP_FROM")
    proveedor = (cfg.get("WHATSAPP_PROVIDER") or "").strip().lower()

    if not proveedor:
        if apikey:
            proveedor = "callmebot"
        elif sid and token and remitente:
            proveedor = "twilio"

    if proveedor == "callmebot":
        if not apikey:
            return False, "Falta CALLMEBOT_APIKEY en .env."
        return _whatsapp_callmebot(apikey, destino, texto)

    if proveedor == "twilio":
        if not (sid and token and remitente):
            return False, "Faltan TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN o TWILIO_WHATSAPP_FROM en .env."
        return _whatsapp_twilio(sid, token, remitente, destino, texto)

    return False, (
        "WhatsApp no está configurado. Añade las credenciales de Twilio "
        "o CALLMEBOT_APIKEY en .env."
    )


def enviar_telegram(app, chat_id: str, mensaje: str) -> tuple[bool, str]:
    """Envía un mensaje a un chat de Telegram usando el token del .env."""
    token = app.config.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return False, "Falta TELEGRAM_BOT_TOKEN en .env."
    if not chat_id:
        return False, "Falta el chat ID de Telegram."
    try:
        respuesta = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": mensaje,
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"Error de conexión con Telegram: {exc}"
    if respuesta.status_code >= 400:
        return False, f"Telegram respondió HTTP {respuesta.status_code}: {respuesta.text[:200]}"
    return True, "Mensaje de Telegram enviado."


def despachar(app, asunto: str, mensaje: str, enlace: str | None) -> dict[str, tuple[bool, str]]:
    """Envía la notificación por los canales activos y devuelve el resultado."""
    canales = Setting.get_list("notify_channel")
    if not canales:
        canales = [c.strip() for c in (app.config.get("NOTIFY_CHANNEL") or "").split(",") if c.strip()]

    resultados: dict[str, tuple[bool, str]] = {}

    if "ntfy" in canales:
        servidor = Setting.get("ntfy_server") or app.config["NTFY_SERVER"]
        tema = Setting.get("ntfy_topic") or app.config["NTFY_TOPIC"]
        resultados["ntfy"] = enviar_ntfy(servidor, tema, asunto, mensaje, enlace)

    if "email" in canales:
        destinatario = Setting.get("email_to") or app.config["EMAIL_TO"]
        resultados["email"] = enviar_email(app, destinatario, asunto, mensaje, enlace)

    if "whatsapp" in canales:
        destino = Setting.get("whatsapp_to") or app.config["WHATSAPP_TO"]
        resultados["whatsapp"] = enviar_whatsapp(app, destino, mensaje, enlace)

    if "telegram" in canales:
        chat_id = Setting.get("telegram_chat_id") or app.config["TELEGRAM_CHAT_ID"]
        texto = mensaje if not enlace else f"{mensaje}\n\nEnlace: {enlace}"
        resultados["telegram"] = enviar_telegram(app, chat_id, texto)

    return resultados

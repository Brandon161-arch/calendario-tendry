"""Rutas web: panel, configuración, historial y acciones."""

import re
import threading
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from . import notifier, scheduler
from .extensions import db
from .models import (
    BotState,
    CheckLog,
    Detection,
    Setting,
    TargetURL,
)
from .scraper import run_check
from .utils import es_url_valida, parsear_keywords, parsear_urls

bp = Blueprint("main", __name__)

ETIQUETAS_RESULTADO = {
    "never": "Sin revisiones todavía",
    "found": "Calendario detectado",
    "pending": "Próximamente / agotado",
    "not_found": "Aún no aparece",
    "error": "Error en la revisión",
    "sin_urls": "Sin URLs configuradas",
    "busy": "Revisión en curso",
}


def _estado_canales(app) -> dict:
    """Indica qué canales tienen credenciales completas en el .env."""
    twilio_listo = bool(
        app.config.get("TWILIO_ACCOUNT_SID")
        and app.config.get("TWILIO_AUTH_TOKEN")
        and app.config.get("TWILIO_WHATSAPP_FROM")
    )
    callmebot_listo = bool(app.config.get("CALLMEBOT_APIKEY"))
    proveedor = (app.config.get("WHATSAPP_PROVIDER") or "").strip().lower()
    if not proveedor:
        proveedor = "callmebot" if callmebot_listo else ("twilio" if twilio_listo else "")

    return {
        "smtp": bool(app.config.get("SMTP_HOST") and app.config.get("SMTP_USER") and app.config.get("SMTP_PASSWORD")),
        "telegram": bool(app.config.get("TELEGRAM_BOT_TOKEN")),
        "whatsapp": twilio_listo or callmebot_listo,
        "whatsapp_provider": "Twilio" if proveedor == "twilio" else ("CallMeBot" if proveedor == "callmebot" else "sin configurar"),
    }


@bp.get("/")
def dashboard():
    estado = BotState.get()
    proximo = scheduler.proxima_ejecucion() or estado.next_check_at
    objetivos = TargetURL.query.filter_by(active=True).order_by(TargetURL.id).all()
    logs = CheckLog.query.order_by(CheckLog.checked_at.desc()).limit(8).all()
    detecciones = Detection.query.order_by(Detection.first_seen_at.desc()).limit(5).all()

    # Tienda a mostrar al final: la configurada o la primera URL web rastreada.
    tienda_url = Setting.get("store_url") or ""
    if not tienda_url:
        for objetivo in objetivos:
            sin_parametros = objetivo.url.lower().split("?")[0].rstrip("/")
            if not sin_parametros.endswith(".xml"):
                tienda_url = objetivo.url
                break
    tienda_dominio = urlparse(tienda_url).netloc if tienda_url else ""
    intervalo = Setting.get_int("interval_minutes", current_app.config["CHECK_INTERVAL_MINUTES"])

    return render_template(
        "dashboard.html",
        estado=estado,
        proximo=proximo,
        objetivos=objetivos,
        logs=logs,
        detecciones=detecciones,
        etiquetas=ETIQUETAS_RESULTADO,
        tienda_url=tienda_url,
        tienda_dominio=tienda_dominio,
        intervalo=intervalo,
        scheduler_activo=scheduler.esta_activo(),
    )


def _leer_formulario() -> dict:
    return {
        "urls": request.form.get("urls", "").strip(),
        "keywords": request.form.get("keywords", "").strip(),
        "interval": request.form.get("interval", "15").strip(),
        "channels": request.form.getlist("channels"),
        "ntfy_topic": request.form.get("ntfy_topic", "").strip(),
        "email_to": request.form.get("email_to", "").strip(),
        "whatsapp_to": request.form.get("whatsapp_to", "").strip(),
        "telegram_chat_id": request.form.get("telegram_chat_id", "").strip(),
        "store_url": request.form.get("store_url", "").strip(),
    }


def _validar_formulario(formulario: dict) -> tuple[list[str], dict]:
    """Valida los campos y devuelve (errores, datos limpios)."""
    errores: list[str] = []
    datos: dict = {}

    # URLs
    urls: list[tuple[str, str]] = []
    for numero, linea in enumerate(formulario["urls"].splitlines(), start=1):
        linea = linea.strip()
        if not linea:
            continue
        etiqueta, url = "", linea
        if "|" in linea:
            etiqueta, url = (parte.strip() for parte in linea.split("|", 1))
        if not es_url_valida(url):
            errores.append(f"URL no válida en la línea {numero}: {url}")
            continue
        urls.append((etiqueta or f"Sitio {len(urls) + 1}", url))
    if not urls:
        errores.append("Añade al menos una URL para rastrear.")
    datos["urls"] = urls

    # Tienda para la vista incrustada (opcional)
    tienda = formulario["store_url"]
    if tienda and not es_url_valida(tienda):
        errores.append("La URL de la tienda no es válida (debe empezar por http:// o https://).")
    datos["store_url"] = tienda

    # Palabras clave
    keywords = parsear_keywords(formulario["keywords"])
    if not keywords:
        errores.append("Añade al menos una palabra clave.")
    datos["keywords"] = keywords

    # Intervalo
    try:
        intervalo = int(formulario["interval"])
        if not 1 <= intervalo <= 1440:
            raise ValueError
    except ValueError:
        errores.append("El intervalo debe ser un número entre 1 y 1440 minutos.")
        intervalo = 15
    datos["interval"] = intervalo

    # Canales
    canales = [c for c in formulario["channels"] if c in {"ntfy", "email", "whatsapp", "telegram"}]
    if not canales:
        errores.append("Selecciona al menos un canal de notificación.")
    datos["channels"] = canales

    # ntfy
    tema = formulario["ntfy_topic"]
    if "ntfy" in canales and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tema):
        errores.append("El tema de ntfy debe tener 1-64 caracteres: letras, números, guion o guion bajo.")
    datos["ntfy_topic"] = tema

    # Correo
    correo = formulario["email_to"]
    if "email" in canales and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        errores.append("Introduce un correo destinatario válido.")
    datos["email_to"] = correo

    # WhatsApp
    whatsapp = formulario["whatsapp_to"]
    if "whatsapp" in canales and not re.fullmatch(r"\+?[0-9][0-9\s().-]{5,24}", whatsapp):
        errores.append("Introduce un WhatsApp válido con prefijo de país (ej. +34600111222).")
    datos["whatsapp_to"] = whatsapp

    # Telegram
    chat_id = formulario["telegram_chat_id"]
    if "telegram" in canales and not re.fullmatch(r"-?\d{3,}", chat_id):
        errores.append("El chat ID de Telegram debe ser numérico (puede empezar por -).")
    datos["telegram_chat_id"] = chat_id

    return errores, datos


def _sync_objetivos(urls: list[tuple[str, str]]) -> None:
    """Crea, actualiza o desactiva las URLs sin perder el historial."""
    todos = TargetURL.query.all()
    por_url = {objetivo.url.rstrip("/"): objetivo for objetivo in todos}
    vistos: set[str] = set()

    for etiqueta, url in urls:
        clave = url.rstrip("/")
        vistos.add(clave)
        existente = por_url.get(clave)
        if existente is None:
            db.session.add(TargetURL(label=etiqueta, url=url, active=True))
        else:
            existente.label = etiqueta
            existente.url = url
            existente.active = True

    for objetivo in todos:
        if objetivo.active and objetivo.url.rstrip("/") not in vistos:
            objetivo.active = False


def _guardar_configuracion(app, datos: dict) -> None:
    Setting.set("keywords", "\n".join(datos["keywords"]))
    Setting.set("interval_minutes", str(datos["interval"]))
    Setting.set("notify_channel", ",".join(datos["channels"]))
    Setting.set("ntfy_topic", datos["ntfy_topic"])
    Setting.set("email_to", datos["email_to"])
    Setting.set("whatsapp_to", datos["whatsapp_to"])
    Setting.set("telegram_chat_id", datos["telegram_chat_id"])
    Setting.set("store_url", datos["store_url"])

    _sync_objetivos(datos["urls"])
    db.session.commit()
    scheduler.reprogramar(app)


def _formulario_actual() -> dict:
    """Carga la configuración actual en el formato del formulario."""
    objetivos = TargetURL.query.filter_by(active=True).order_by(TargetURL.id).all()
    return {
        "urls": "\n".join(
            f"{objetivo.label} | {objetivo.url}" if objetivo.label else objetivo.url
            for objetivo in objetivos
        ),
        "keywords": "\n".join(Setting.get_list("keywords")),
        "interval": Setting.get("interval_minutes") or str(current_app.config["CHECK_INTERVAL_MINUTES"]),
        "channels": Setting.get_list("notify_channel"),
        "ntfy_topic": Setting.get("ntfy_topic") or "",
        "email_to": Setting.get("email_to") or "",
        "whatsapp_to": Setting.get("whatsapp_to") or "",
        "telegram_chat_id": Setting.get("telegram_chat_id") or "",
        "store_url": Setting.get("store_url") or "",
    }


@bp.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    canales = _estado_canales(current_app)

    if request.method == "POST":
        formulario = _leer_formulario()
        errores, datos = _validar_formulario(formulario)
        if errores:
            for error in errores:
                flash(error, "error")
            return render_template(
                "settings.html",
                form=formulario,
                canales=canales,
            )

        _guardar_configuracion(current_app, datos)

        if "email" in datos["channels"] and not canales["smtp"]:
            flash("Correo activado, pero faltan datos SMTP en .env.", "warning")
        if "whatsapp" in datos["channels"] and not canales["whatsapp"]:
            flash("WhatsApp activado, pero faltan credenciales de Twilio o CallMeBot en .env.", "warning")
        if "telegram" in datos["channels"] and not canales["telegram"]:
            flash("Telegram activado, pero falta TELEGRAM_BOT_TOKEN en .env.", "warning")

        flash("Configuración guardada correctamente.", "success")
        return redirect(url_for("main.configuracion"))

    return render_template(
        "settings.html",
        form=_formulario_actual(),
        canales=canales,
    )


@bp.get("/historial")
def historial():
    pagina = max(1, request.args.get("page", 1, type=int))
    logs = (
        CheckLog.query.order_by(CheckLog.checked_at.desc())
        .paginate(page=pagina, per_page=20, error_out=False)
    )
    detecciones = Detection.query.order_by(Detection.first_seen_at.desc()).limit(30).all()
    resumen = {
        "hallazgos": Detection.query.count(),
        "notificados": Detection.query.filter(Detection.notified_at.isnot(None)).count(),
        "revisiones": CheckLog.query.count(),
    }
    return render_template(
        "history.html",
        logs=logs,
        detecciones=detecciones,
        etiquetas=ETIQUETAS_RESULTADO,
        resumen=resumen,
    )


def _revision_en_hilo(app) -> None:
    run_check(app)


@bp.post("/acciones/revisar")
def revisar_ahora():
    estado = BotState.get()
    if not estado.running:
        flash("El rastreo está pausado. Reanúdalo antes de revisar.", "warning")
        return redirect(url_for("main.dashboard"))

    app = current_app._get_current_object()
    threading.Thread(target=_revision_en_hilo, args=(app,), daemon=True).start()
    flash("Revisión iniciada en segundo plano. Actualiza en unos segundos.", "info")
    return redirect(url_for("main.dashboard"))


@bp.post("/acciones/alternar")
def alternar_rastreo():
    estado = BotState.get()
    estado.running = not estado.running
    db.session.commit()

    if estado.running:
        scheduler.reanudar()
        flash("Rastreo reanudado.", "success")
    else:
        scheduler.pausar()
        flash("Rastreo pausado.", "info")
    return redirect(url_for("main.dashboard"))


@bp.post("/acciones/probar-notificacion")
def probar_notificacion():
    app = current_app
    resultados = notifier.despachar(
        app,
        "Notificación de prueba - Tendry",
        "Si recibes este mensaje, el rastreador podrá avisarte cuando salga el calendario. "
        "Este es solo un mensaje de prueba.",
        url_for("main.dashboard", _external=True),
    )
    exitos = [canal for canal, (ok, _) in resultados.items() if ok]
    if exitos:
        flash(f"Notificación de prueba enviada por: {', '.join(exitos)}.", "success")
    else:
        detalle = "; ".join(f"{canal}: {mensaje}" for canal, (_, mensaje) in resultados.items())
        flash(f"No se pudo enviar la prueba. {detalle or 'No hay canales configurados.'}", "error")
    return redirect(url_for("main.dashboard"))


@bp.post("/acciones/probar-correo")
def probar_correo():
    destino = Setting.get("email_to") or current_app.config["EMAIL_TO"]
    if not destino:
        flash("Guarda primero un correo destinatario en Configuración.", "warning")
        return redirect(url_for("main.configuracion"))

    ok, detalle = notifier.enviar_email(
        current_app,
        destino,
        "Notificación de prueba - Tendry",
        "Si recibes este correo, el aviso por email está listo. Cuando aparezca el "
        "calendario, te enviaremos el enlace directo.",
        url_for("main.dashboard", _external=True),
    )
    if ok:
        flash(f"Correo de prueba enviado a {destino}.", "success")
    else:
        flash(f"No se pudo enviar el correo. {detalle}", "error")
    return redirect(url_for("main.configuracion"))


@bp.post("/acciones/probar-whatsapp")
def probar_whatsapp():
    destino = Setting.get("whatsapp_to") or current_app.config["WHATSAPP_TO"]
    if not destino:
        flash("Guarda primero tu número de WhatsApp en Configuración.", "warning")
        return redirect(url_for("main.configuracion"))

    ok, detalle = notifier.enviar_whatsapp(
        current_app,
        destino,
        "Notificación de prueba - Tendry. Si recibes este WhatsApp, el rastreador "
        "podrá avisarte cuando salga el calendario.",
        url_for("main.dashboard", _external=True),
    )
    if ok:
        flash(f"WhatsApp de prueba enviado a {destino}.", "success")
    else:
        flash(f"No se pudo enviar el WhatsApp. {detalle}", "error")
    return redirect(url_for("main.configuracion"))


@bp.post("/acciones/reiniciar-alerta")
def reiniciar_alerta():
    Detection.query.delete()
    estado = BotState.get()
    estado.calendar_found = False
    estado.last_match_url = None
    estado.last_match_term = None
    db.session.commit()
    flash("Alerta reiniciada. La próxima detección volverá a notificar.", "success")
    return redirect(url_for("main.dashboard"))


@bp.post("/acciones/limpiar-historial")
def limpiar_historial():
    CheckLog.query.delete()
    db.session.commit()
    flash("Historial de revisiones borrado.", "success")
    return redirect(url_for("main.historial"))

"""Descarga de páginas y lógica de detección del calendario de adviento."""

from __future__ import annotations

import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .extensions import db
from .models import (
    BotState,
    CheckLog,
    Detection,
    ProductState,
    Setting,
    TargetURL,
    utcnow,
)
from .utils import contiene_keyword, normalizar

# Indicadores textuales de disponibilidad (se comparan ya normalizados).
MARCAS_NO_DISPONIBLE = (
    "agotado",
    "sin stock",
    "no disponible",
    "proximamente",
    "coming soon",
    "sold out",
    "out of stock",
    "notify me",
    "avisame",
    "lista de espera",
)
MARCAS_DISPONIBLE = (
    "anadir al carrito",
    "add to cart",
    "add to bag",
    "comprar ahora",
    "buy now",
    "en stock",
    "in stock",
)

MAX_EXTRACTO = 300
CHECK_LOCK = threading.Lock()


class ScrapeError(Exception):
    """Error controlado de descarga o respuesta HTTP."""

    def __init__(self, mensaje: str, status_code: int | None = None):
        super().__init__(mensaje)
        self.status_code = status_code


@dataclass
class Candidato:
    """Posible hallazgo detectado en una página."""

    kind: str
    term: str
    link: str
    page_url: str
    dedupe_key: str
    estado: str = "found"  # found | pending
    snippet: str = ""


@dataclass
class Analisis:
    """Resultado del análisis de una URL."""

    url: str
    resultado: str = "not_found"
    candidatos: list[Candidato] = field(default_factory=list)
    termino: str | None = None
    enlace: str | None = None

    def recalcular(self) -> "Analisis":
        encontrados = [c for c in self.candidatos if c.estado == "found"]
        if encontrados:
            self.resultado = "found"
            self.termino = encontrados[0].term
            self.enlace = encontrados[0].link
        elif any(c.estado == "pending" for c in self.candidatos):
            self.resultado = "pending"
            self.termino = self.candidatos[0].term
            self.enlace = self.candidatos[0].link
        else:
            self.resultado = "not_found"
        return self


def crear_sesion(user_agent: str) -> requests.Session:
    """Sesión HTTP con cabeceras realistas."""
    sesion = requests.Session()
    sesion.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
    )
    return sesion


def fetch_page(sesion: requests.Session, url: str, timeout: int) -> tuple[int, str]:
    """Descarga una URL y devuelve (código HTTP, texto)."""
    try:
        respuesta = sesion.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        raise ScrapeError(f"Error de conexión: {exc}") from exc

    if respuesta.status_code >= 400:
        raise ScrapeError(f"HTTP {respuesta.status_code}", status_code=respuesta.status_code)

    # Algunos servidores mandan latin-1 por defecto; intentamos detectar mejor.
    if not respuesta.encoding or respuesta.encoding.lower() in {"iso-8859-1", "ascii"}:
        respuesta.encoding = respuesta.apparent_encoding or "utf-8"
    return respuesta.status_code, respuesta.text


def es_sitemap(url: str, texto: str) -> bool:
    """Heurística para saber si la respuesta es un sitemap XML."""
    ruta = urlparse(url).path.lower()
    inicio = texto.lstrip()[:500].lower()
    return (
        ruta.endswith(".xml")
        or "sitemap" in ruta
        or inicio.startswith("<?xml")
        or "<urlset" in inicio
        or "<sitemapindex" in inicio
    )


def texto_visible(soup: BeautifulSoup) -> str:
    """Extrae texto legible eliminando scripts, estilos y plantillas."""
    for etiqueta in soup(["script", "style", "noscript", "template"]):
        etiqueta.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def check_availability(html: str) -> str:
    """Devuelve available, unavailable o unknown según los textos de la página."""
    soup = BeautifulSoup(html, "html.parser")
    texto = normalizar(texto_visible(soup))
    no_disponible = any(marca in texto for marca in MARCAS_NO_DISPONIBLE)
    disponible = any(marca in texto for marca in MARCAS_DISPONIBLE)
    if no_disponible and not disponible:
        return "unavailable"
    if disponible and not no_disponible:
        return "available"
    return "unknown"


def analizar_pagina(url: str, html: str, keywords: list[str]) -> Analisis:
    """Busca palabras clave en el texto y en los enlaces de una página HTML."""
    soup = BeautifulSoup(html, "html.parser")
    texto = texto_visible(soup)
    disponibilidad = check_availability(html)
    estado_base = "pending" if disponibilidad == "unavailable" else "found"

    analisis = Analisis(url=url)

    termino = contiene_keyword(texto, keywords)
    if termino:
        analisis.candidatos.append(
            Candidato(
                kind="keyword",
                term=termino,
                link=url,
                page_url=url,
                dedupe_key=f"keyword|{normalizar(url)}",
                estado=estado_base,
                snippet=texto[:MAX_EXTRACTO],
            )
        )

    vistos: set[str] = set()
    for enlace in soup.find_all("a", href=True):
        nombre = " ".join(enlace.get_text(" ", strip=True).split())
        if not nombre:
            nombre = " ".join((enlace.get("title") or "").split())
        if not nombre:
            imagen = enlace.find("img", alt=True)
            nombre = (imagen.get("alt") or "").strip() if imagen else ""
        if not nombre:
            continue

        termino_enlace = contiene_keyword(nombre, keywords)
        if not termino_enlace:
            continue

        href = urljoin(url, enlace["href"])
        if urlparse(href).scheme not in {"http", "https"}:
            continue

        clave = normalizar(href)
        if clave in vistos:
            continue
        vistos.add(clave)

        analisis.candidatos.append(
            Candidato(
                kind="link",
                term=nombre[:200],
                link=href,
                page_url=url,
                dedupe_key=f"link|{clave}",
                estado="found",
                snippet=texto[:MAX_EXTRACTO],
            )
        )

    return analisis.recalcular()


def analizar_sitemap(url: str, texto: str, keywords: list[str]) -> Analisis:
    """Busca palabras clave en las URLs de un sitemap XML."""
    analisis = Analisis(url=url)
    try:
        raiz = ET.fromstring(texto.encode("utf-8"))
        locs = [
            elemento.text.strip()
            for elemento in raiz.iter()
            if elemento.tag.lower().endswith("loc") and elemento.text
        ]
    except ET.ParseError:
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", texto, flags=re.I | re.S)

    vistos: set[str] = set()
    for loc in locs:
        loc = loc.strip()
        if not loc or loc in vistos:
            continue
        vistos.add(loc)
        termino = contiene_keyword(loc, keywords)
        if not termino:
            continue
        analisis.candidatos.append(
            Candidato(
                kind="sitemap",
                term=termino,
                link=loc,
                page_url=url,
                dedupe_key=f"sitemap|{normalizar(loc)}",
                estado="found",
                snippet=loc[:MAX_EXTRACTO],
            )
        )

    return analisis.recalcular()


def _pausa(cfg) -> None:
    """Espera entre peticiones para no saturar el sitio."""
    base = max(0.0, float(cfg.get("REQUEST_DELAY_SECONDS", 2)))
    time.sleep(base + random.uniform(0, 1))


def _intervalo(cfg) -> int:
    """Intervalo actual en minutos (configuración web > .env)."""
    try:
        return max(1, int(Setting.get("interval_minutes") or cfg["CHECK_INTERVAL_MINUTES"]))
    except (TypeError, ValueError):
        return int(cfg["CHECK_INTERVAL_MINUTES"])


def _procesar_productos(sesion: requests.Session, analisis: Analisis, cfg) -> None:
    """Revisa páginas de producto enlazadas y detecta cambios de disponibilidad."""
    limite = max(0, int(cfg.get("MAX_PRODUCT_PAGES", 5)))
    enlaces = [c for c in analisis.candidatos if c.kind == "link"][:limite]

    for enlace in enlaces:
        _pausa(cfg)
        try:
            _, html_producto = fetch_page(sesion, enlace.link, cfg["REQUEST_TIMEOUT"])
        except ScrapeError:
            continue

        disponibilidad = check_availability(html_producto)
        if disponibilidad == "unknown":
            continue

        clave = normalizar(enlace.link)
        registro = ProductState.query.filter_by(product_key=clave).first()
        ahora = utcnow()

        if registro is None:
            # Primera vez visto: se guarda como línea base sin notificar.
            db.session.add(
                ProductState(
                    product_key=clave,
                    url=enlace.link,
                    name=enlace.term[:255],
                    availability=disponibilidad,
                    first_seen_at=ahora,
                    last_seen_at=ahora,
                )
            )
        else:
            if registro.availability == "unavailable" and disponibilidad == "available":
                analisis.candidatos.append(
                    Candidato(
                        kind="availability",
                        term=registro.name or enlace.term,
                        link=enlace.link,
                        page_url=analisis.url,
                        dedupe_key=f"availability|{clave}",
                        estado="found",
                        snippet="Antes estaba agotado o próximamente; ahora está disponible.",
                    )
                )
            registro.availability = disponibilidad
            registro.last_seen_at = ahora

        if disponibilidad == "unavailable":
            enlace.estado = "pending"


def _registrar_error(target: TargetURL, exc: ScrapeError) -> None:
    """Guarda un error en el historial y en la URL rastreada."""
    ahora = utcnow()
    db.session.add(
        CheckLog(
            target_id=target.id,
            url=target.url,
            checked_at=ahora,
            result="error",
            http_status=exc.status_code,
            error=str(exc)[:1000],
        )
    )
    target.last_checked_at = ahora
    target.last_status = "error"
    target.last_http_status = exc.status_code
    target.last_error = str(exc)[:1000]


def _registrar_detecciones(analisis: Analisis, nuevas: list[Detection]) -> None:
    """Guarda hallazgos nuevos y devuelve los que aún no se han notificado."""
    ahora = utcnow()
    ids_pendientes = {deteccion.id for deteccion in nuevas}

    for candidato in analisis.candidatos:
        if candidato.estado != "found":
            continue
        deteccion = Detection.query.filter_by(dedupe_key=candidato.dedupe_key).first()
        if deteccion is None:
            deteccion = Detection(
                dedupe_key=candidato.dedupe_key[:512],
                kind=candidato.kind,
                url=candidato.page_url[:1024],
                matched_term=(candidato.term or "")[:255],
                link=candidato.link[:1024] if candidato.link else None,
                snippet=(candidato.snippet or "")[:1000],
                first_seen_at=ahora,
                last_seen_at=ahora,
            )
            db.session.add(deteccion)
            db.session.flush()
        else:
            deteccion.last_seen_at = ahora

        if deteccion.notified_at is None and deteccion.id not in ids_pendientes:
            nuevas.append(deteccion)
            ids_pendientes.add(deteccion.id)


def _notificar_nuevas(app, nuevas: list[Detection]) -> tuple[bool, str]:
    """Envía una única notificación agrupando los hallazgos del ciclo."""
    from . import notifier

    primera = nuevas[0]
    enlace = primera.link or primera.url
    lineas = [f"- {d.matched_term} ({d.url})" for d in nuevas[:5]]
    if len(nuevas) > 5:
        lineas.append(f"... y {len(nuevas) - 5} hallazgo(s) más")
    mensaje = (
        "Se detectó el calendario de adviento de Tendry.\n\n"
        + "\n".join(lineas)
        + f"\n\nEnlace directo: {enlace}"
    )

    resultados = notifier.despachar(
        app,
        "Calendario de Adviento disponible",
        mensaje,
        enlace,
    )
    exitos = [canal for canal, (ok, _) in resultados.items() if ok]
    if exitos:
        return True, f"Notificado por: {', '.join(exitos)}"
    detalle = "; ".join(f"{canal}: {mensaje}" for canal, (_, mensaje) in resultados.items())
    return False, detalle or "No hay canales de notificación configurados."


def _ejecutar_revision(app) -> dict:
    """Realiza un ciclo completo de revisión y devuelve un resumen."""
    cfg = app.config
    estado = BotState.get()
    if not estado.running:
        return {"status": "paused"}

    keywords = Setting.get_list("keywords")
    if not keywords:
        keywords = [k.strip() for k in (cfg["DEFAULT_KEYWORDS"] or "").split(",") if k.strip()]

    objetivos = TargetURL.query.filter_by(active=True).order_by(TargetURL.id).all()
    ahora = utcnow()
    estado.last_check_at = ahora
    intervalo = _intervalo(cfg)

    if not objetivos:
        estado.last_result = "sin_urls"
        estado.next_check_at = ahora + timedelta(minutes=intervalo)
        db.session.commit()
        return {"status": "sin_urls"}

    sesion = crear_sesion(cfg["USER_AGENT"])
    nuevas: list[Detection] = []
    encontrados = pendientes = errores = 0
    ultimo_error: str | None = None

    try:
        for indice, target in enumerate(objetivos):
            if indice > 0:
                _pausa(cfg)
            try:
                codigo, texto = fetch_page(sesion, target.url, cfg["REQUEST_TIMEOUT"])
                if es_sitemap(target.url, texto):
                    analisis = analizar_sitemap(target.url, texto, keywords)
                else:
                    analisis = analizar_pagina(target.url, texto, keywords)
                    _procesar_productos(sesion, analisis, cfg)
                    analisis.recalcular()

                if analisis.resultado == "found":
                    encontrados += 1
                elif analisis.resultado == "pending":
                    pendientes += 1

                ahora = utcnow()
                db.session.add(
                    CheckLog(
                        target_id=target.id,
                        url=target.url,
                        checked_at=ahora,
                        result=analisis.resultado,
                        http_status=codigo,
                        matched_term=(analisis.termino or "")[:255] or None,
                        matched_link=(analisis.enlace or "")[:1024] or None,
                    )
                )
                target.last_checked_at = ahora
                target.last_status = analisis.resultado
                target.last_http_status = codigo
                target.last_error = None

                _registrar_detecciones(analisis, nuevas)
            except ScrapeError as exc:
                errores += 1
                ultimo_error = str(exc)
                _registrar_error(target, exc)
            except Exception as exc:  # noqa: BLE001 - el bot no debe caerse
                errores += 1
                ultimo_error = f"Error inesperado: {exc}"
                _registrar_error(target, ScrapeError(ultimo_error))
    finally:
        sesion.close()

    if encontrados:
        estado.last_result = "found"
    elif pendientes:
        estado.last_result = "pending"
    elif errores and errores == len(objetivos):
        estado.last_result = "error"
    else:
        estado.last_result = "not_found"
    estado.last_error = ultimo_error if estado.last_result == "error" else None

    if nuevas:
        ok, detalle = _notificar_nuevas(app, nuevas)
        if ok:
            momento = utcnow()
            for deteccion in nuevas:
                deteccion.notified_at = momento
            estado.calendar_found = True
            estado.last_match_url = nuevas[0].link or nuevas[0].url
            estado.last_match_term = nuevas[0].matched_term
            app.logger.info("Notificación enviada: %s", detalle)
        else:
            app.logger.warning("No se pudo notificar: %s", detalle)

    estado.next_check_at = utcnow() + timedelta(minutes=intervalo)
    db.session.commit()
    return {
        "status": estado.last_result,
        "found": encontrados,
        "pending": pendientes,
        "errors": errores,
    }


def run_check(app) -> dict:
    """Punto de entrada seguro: evita dos revisiones simultáneas."""
    if not CHECK_LOCK.acquire(blocking=False):
        return {"status": "busy", "message": "Ya hay una revisión en curso."}
    try:
        with app.app_context():
            return _ejecutar_revision(app)
    finally:
        CHECK_LOCK.release()

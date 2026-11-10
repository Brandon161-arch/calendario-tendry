"""Utilidades comunes: texto, URLs, validación y CSRF."""

import re
import secrets
import unicodedata
from urllib.parse import urlparse

from flask import abort, request, session


def quitar_acentos(texto: str) -> str:
    """Convierte tildes y diéresis a letras base."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Normaliza para comparar: minúsculas, sin acentos y con espacios simples."""
    if not texto:
        return ""
    return " ".join(quitar_acentos(str(texto)).lower().split())


def contiene_keyword(texto: str, keywords: list[str]) -> str | None:
    """Devuelve la primera palabra clave encontrada en el texto, o None."""
    normalizado = normalizar(texto)
    if not normalizado:
        return None
    for keyword in keywords:
        clave = normalizar(keyword)
        if clave and clave in normalizado:
            return keyword
    return None


def es_url_valida(url: str) -> bool:
    """Comprueba que sea una URL http(s) con host."""
    try:
        partes = urlparse(url.strip())
    except ValueError:
        return False
    return partes.scheme in {"http", "https"} and bool(partes.netloc)


def parsear_urls(texto: str) -> list[tuple[str, str]]:
    """Convierte líneas 'Etiqueta | URL' o 'URL' en pares (etiqueta, url)."""
    resultado: list[tuple[str, str]] = []
    for numero, linea in enumerate((texto or "").splitlines(), start=1):
        linea = linea.strip()
        if not linea:
            continue
        etiqueta, url = "", linea
        if "|" in linea:
            etiqueta, url = (parte.strip() for parte in linea.split("|", 1))
        if es_url_valida(url):
            resultado.append((etiqueta or f"Sitio {numero}", url))
    return resultado


def parsear_keywords(texto: str) -> list[str]:
    """Acepta palabras clave separadas por líneas o comas y elimina duplicados."""
    vistos: set[str] = set()
    resultado: list[str] = []
    for trozo in re.split(r"[\n,]+", texto or ""):
        limpio = trozo.strip()
        clave = normalizar(limpio)
        if limpio and clave not in vistos:
            vistos.add(clave)
            resultado.append(limpio)
    return resultado


def token_csrf() -> str:
    """Devuelve (y crea si hace falta) el token CSRF de la sesión."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def validar_csrf() -> None:
    """Protege todas las peticiones POST con un token de sesión."""
    if request.method != "POST":
        return
    enviado = request.form.get("_csrf_token", "")
    guardado = session.get("_csrf_token", "")
    if not guardado or not secrets.compare_digest(enviado, guardado):
        abort(400, description="Token CSRF inválido o caducado.")

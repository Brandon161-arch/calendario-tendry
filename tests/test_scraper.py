"""Pruebas de la lógica de detección con HTML de ejemplo."""

from pathlib import Path

from app.scraper import analizar_pagina, analizar_sitemap, check_availability

FIXTURES = Path(__file__).parent / "fixtures"
KEYWORDS = ["calendario de adviento", "advent calendar", "adviento"]
BASE = "https://tendry.test/"


def leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def test_pagina_sin_calendario_no_detecta_nada():
    analisis = analizar_pagina(BASE, leer("sin_calendario.html"), KEYWORDS)
    assert analisis.resultado == "not_found"
    assert analisis.candidatos == []


def test_keyword_en_texto_detecta_calendario():
    analisis = analizar_pagina(BASE, leer("con_keyword.html"), KEYWORDS)
    assert analisis.resultado == "found"
    assert any(c.kind == "keyword" for c in analisis.candidatos)
    assert analisis.termino.lower().startswith("calendario")


def test_deteccion_ignora_mayusculas_y_acentos():
    html = "<html><body><h1>CALENDARIO DE ADVIENTO</h1><p>Muy pronto</p></body></html>"
    analisis = analizar_pagina(BASE, html, ["calendario de adviento"])
    assert analisis.resultado == "found"


def test_enlace_de_producto_detecta_calendario():
    analisis = analizar_pagina(BASE, leer("con_enlace_producto.html"), KEYWORDS)
    assert analisis.resultado == "found"
    enlaces = [c for c in analisis.candidatos if c.kind == "link"]
    assert enlaces
    assert enlaces[0].link == "https://tendry.test/productos/calendario-de-adviento-tendry"


def test_enlaces_sin_keyword_no_se_marcan():
    analisis = analizar_pagina(BASE, leer("sin_calendario.html"), KEYWORDS)
    assert not any(c.kind == "link" for c in analisis.candidatos)


def test_producto_agotado_queda_pendiente():
    analisis = analizar_pagina(BASE, leer("producto_agotado.html"), KEYWORDS)
    assert analisis.resultado == "pending"
    assert all(c.estado == "pending" for c in analisis.candidatos)


def test_producto_disponible_se_detecta():
    analisis = analizar_pagina(BASE, leer("producto_disponible.html"), KEYWORDS)
    assert analisis.resultado == "found"


def test_check_availability_distingue_estados():
    assert check_availability(leer("producto_agotado.html")) == "unavailable"
    assert check_availability(leer("producto_disponible.html")) == "available"
    assert check_availability(leer("sin_calendario.html")) == "unknown"


def test_sitemap_detecta_url_con_keyword():
    analisis = analizar_sitemap(
        "https://tendry.test/sitemap.xml",
        leer("sitemap.xml"),
        KEYWORDS,
    )
    assert analisis.resultado == "found"
    assert len(analisis.candidatos) == 1
    assert "calendario-de-adviento" in analisis.candidatos[0].link


def test_html_roto_no_lanza_excepcion():
    analisis = analizar_pagina(BASE, "<html><body><p>adviento", KEYWORDS)
    assert analisis.resultado == "found"

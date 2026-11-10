"""Pruebas básicas de las páginas y la protección CSRF."""

from pathlib import Path

from app.models import Detection, TargetURL

FIXTURES = Path(__file__).parent / "fixtures"


def test_panel_responde(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert b"Calendario de Adviento" in respuesta.data


def test_configuracion_responde(client):
    respuesta = client.get("/configuracion")
    assert respuesta.status_code == 200


def test_historial_responde(client):
    respuesta = client.get("/historial")
    assert respuesta.status_code == 200


def test_post_sin_csrf_es_rechazado(client):
    respuesta = client.post("/acciones/alternar")
    assert respuesta.status_code == 400


def test_dashboard_restaura_urls_si_quedan_cero(app):
    from app.extensions import db
    from app.models import TargetURL

    with app.app_context():
        app.config["DEFAULT_URLS"] = (
            "Tienda | https://tendry.test/, "
            "Calendario | https://tendry.test/calendario-de-adviento"
        )
        for objetivo in TargetURL.query.all():
            objetivo.active = False
        db.session.commit()

    respuesta = app.test_client().get("/")
    assert respuesta.status_code == 200

    with app.app_context():
        activas = TargetURL.query.filter_by(active=True).all()
        assert len(activas) == 2
        assert {objetivo.url for objetivo in activas} == {
            "https://tendry.test/",
            "https://tendry.test/calendario-de-adviento",
        }


def test_revision_detecta_y_notifica_una_sola_vez(app, monkeypatch):
    from app import notifier, scraper
    from app.extensions import db

    with app.app_context():
        db.session.add(TargetURL(label="Inicio", url="https://tendry.test/", active=True))
        db.session.commit()

    html = (FIXTURES / "con_keyword.html").read_text(encoding="utf-8")

    monkeypatch.setattr(scraper, "fetch_page", lambda *args, **kwargs: (200, html))
    monkeypatch.setattr(scraper, "_pausa", lambda cfg: None)
    monkeypatch.setattr(scraper, "_procesar_productos", lambda *args, **kwargs: None)

    llamadas = []

    def despachar_falso(*args, **kwargs):
        llamadas.append(1)
        return {"ntfy": (True, "ok")}

    monkeypatch.setattr(notifier, "despachar", despachar_falso)

    scraper.run_check(app)
    scraper.run_check(app)

    with app.app_context():
        assert Detection.query.count() == 1
        assert len(llamadas) == 1

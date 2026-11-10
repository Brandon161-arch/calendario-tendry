"""Programación de las revisiones automáticas con APScheduler."""

import os
from datetime import datetime, timedelta, timezone

from .extensions import scheduler
from .models import BotState, Setting

JOB_ID = "tendry_check"


def intervalo_minutos(app) -> int:
    """Intervalo efectivo en minutos."""
    try:
        return max(1, int(Setting.get("interval_minutes") or app.config["CHECK_INTERVAL_MINUTES"]))
    except (TypeError, ValueError):
        return int(app.config["CHECK_INTERVAL_MINUTES"])


def _ejecutar(app) -> None:
    """Job del scheduler: ejecuta el ciclo de revisión con contexto de app."""
    from .scraper import run_check

    run_check(app)


def iniciar_scheduler(app) -> None:
    """Arranca el scheduler una sola vez y respeta el estado de pausa."""
    if not app.config.get("SCHEDULER_ENABLED", True):
        return
    if app.config.get("TESTING"):
        return
    # Solo se aplica al servidor de desarrollo con reloader: el proceso padre
    # no debe arrancar el scheduler, el hijo sí. Bajo Gunicorn no se aplica.
    if (
        app.debug
        and os.environ.get("TENDRY_RELOADER") == "1"
        and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    ):
        return

    with app.app_context():
        job = scheduler.get_job(JOB_ID)
        if job is None:
            scheduler.add_job(
                _ejecutar,
                trigger="interval",
                minutes=intervalo_minutos(app),
                args=[app],
                id=JOB_ID,
                name="Revisión del calendario de Tendry",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
            )
            job = scheduler.get_job(JOB_ID)

        if not scheduler.running:
            scheduler.start()

        estado = BotState.get()
        if not estado.running:
            scheduler.pause_job(JOB_ID)
        elif job.next_run_time is None:
            # Solo se reanuda si estaba realmente pausado; así no se pierde
            # la primera ejecución programada a los 30 segundos.
            scheduler.resume_job(JOB_ID)


def pausar() -> None:
    """Pausa el job si el scheduler está activo."""
    if scheduler.get_job(JOB_ID):
        scheduler.pause_job(JOB_ID)


def reanudar() -> None:
    """Reanuda el job si el scheduler está activo."""
    if scheduler.get_job(JOB_ID):
        scheduler.resume_job(JOB_ID)


def reprogramar(app) -> None:
    """Aplica un nuevo intervalo sin reiniciar la aplicación."""
    with app.app_context():
        job = scheduler.get_job(JOB_ID)
        if job is not None:
            job.reschedule(trigger="interval", minutes=intervalo_minutos(app))


def proxima_ejecucion() -> datetime | None:
    """Próxima ejecución en UTC naive para mostrarla en la web."""
    job = scheduler.get_job(JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.astimezone(timezone.utc).replace(tzinfo=None)


def esta_activo() -> bool:
    """Indica si el scheduler está arrancado y el job existe."""
    return bool(scheduler.running and scheduler.get_job(JOB_ID) is not None)

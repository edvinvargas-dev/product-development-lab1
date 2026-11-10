"""Consumidor diario: ingesta y validación, preparación, pronóstico y pedido, seguimiento.

Una ejecución por fecha de corte (logical date). `catchup=True` recorre el periodo de
`config/operacion.json`; `airflow backfill create` reprocesa fechas pasadas. Las tareas
solo orquestan: la lógica y sus pruebas están en `src/`.
"""

from datetime import timedelta, timezone

import pendulum
from airflow.sdk import dag, get_current_context, task

from src import operation

CONFIG = operation.load_config()
START = pendulum.parse(CONFIG["operation"]["start_date"], tz="UTC")
END = pendulum.parse(CONFIG["operation"]["end_date"], tz="UTC")


def _config():
    return operation.load_config()


@dag(dag_id="reposicion_diaria", schedule="@daily", start_date=START, end_date=END, catchup=True,
     max_active_runs=1, tags=["laboratorio1", "consumidor"], doc_md=__doc__,
     default_args={"retries": 1, "retry_delay": timedelta(minutes=1), "depends_on_past": True})
def reposicion_diaria():
    @task.sensor(poke_interval=30, timeout=60 * 60 * 3, mode="reschedule", depends_on_past=False)
    def esperar_bandeja():
        """La bandeja la crea el productor externo; el consumidor solo espera a que exista."""
        return (operation.p(_config(), "inbox") / "manifest.json").is_file()

    @task
    def resolver_corte():
        context = get_current_context()
        run = context["dag_run"]
        # Un disparo manual sin logical_date usa run_after; ambos son datetime con zona.
        moment = run.logical_date or run.run_after
        return moment.astimezone(timezone.utc).date().isoformat()

    @task
    def ingesta_y_validacion_entregas(day):
        """Registra entregas disponibles al corte. Valores inválidos -> cuarentena (no detienen
        las demás entregas); un hash alterado detiene la ejecución."""
        return operation.step_ingest(_config(), day)

    @task
    def preparacion_snapshot(day, _ingesta):
        return operation.step_snapshot(_config(), day)

    @task
    def validacion_cruzada(day, _snapshot):
        """Falla ante datos inconsistentes (detiene el flujo antes del modelo). Las ausencias
        esperables del negocio solo generan avisos."""
        return operation.step_validate(_config(), day)

    @task
    def pronostico_y_pedido(day, _validacion):
        return operation.step_publish(_config(), day)

    @task
    def seguimiento(day, _publicacion):
        return operation.step_tracking(_config(), day)

    day = resolver_corte()
    ingested = ingesta_y_validacion_entregas(day)
    esperar_bandeja() >> ingested
    snap = preparacion_snapshot(day, ingested)
    valid = validacion_cruzada(day, snap)
    published = pronostico_y_pedido(day, valid)
    seguimiento(day, published)


reposicion_diaria()

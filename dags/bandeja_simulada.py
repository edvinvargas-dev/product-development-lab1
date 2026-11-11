"""Productor simulado del sistema de origen (externo al consumidor).

Genera una sola vez la bandeja inmutable a partir de los CSV de Kaggle en dataOriginal/.
Si ya existe con la misma configuración no hace nada; con otra configuración falla en
lugar de sobrescribirla. Corre una vez al levantar Airflow (@once).
"""

import pendulum
from airflow.sdk import dag, task

from src import operation


@dag(dag_id="bandeja_simulada", schedule="@once", start_date=pendulum.datetime(2017, 1, 1, tz="UTC"),
     catchup=False, tags=["laboratorio1", "productor"], doc_md=__doc__)
def bandeja_simulada():
    @task
    def generar_bandeja():
        return operation.prepare_inbox(operation.load_config())

    generar_bandeja()


bandeja_simulada()

# Laboratorio 1: motor de reposición

Estado: auditoría, ingesta temporal, entorno Linux y baseline de cuantiles versionado localmente con DVC. El producto completo y Airflow aún no están implementados. Decisiones y supuestos en [DECISIONES.md](DECISIONES.md); requisitos pendientes en [docs/ACEPTACION.md](docs/ACEPTACION.md).

## Recorrido disponible

Desde la raíz del proyecto, en WSL con Python 3.10 o posterior:

```bash
python3 -m unittest discover -s tests -v
python3 -m src.audit
```

Colocar los cinco originales de Kaggle en `dataOriginal/`: `train.csv`, `stores.csv`, `holidays_events.csv`, `oil.csv` y `transactions.csv`. No se requieren ni se leen `test.csv` o `sample_submission.csv`. La auditoría solo lee los originales y genera `reports/generated/audit.json`, ignorado por Git. Repite el comando para reconstruirlo; no equivale todavía a un pipeline DVC.

La auditoría lee train en bloques de 50 000 filas, comprueba claves fecha/tienda/familia, cobertura, faltantes, ceros, negativos y máximos por familia. Su diagnóstico no reemplaza la futura validación de ingesta.

## Recorrido temporal disponible

El [tutorial de ingesta](docs/INGESTA_TEMPORAL.md) explica los supuestos y comandos. `config/simulation.json` define una muestra de julio y la primera semana de agosto de 2017. El productor `src.simulate` genera una bandeja nueva, `src.ingest` registra únicamente entregas disponibles y `src.snapshot` reconstruye los datos conocidos en un corte. Se usan las cinco fuentes; no se requieren paquetes adicionales.

Ya se ejecutaron cortes del 1, 5 y 6 de agosto. Las salidas están bajo `data/`, ignoradas por Git. DVC referencia la bandeja y el registro, y define la reconstrucción del corte del 1 de agosto en un directorio derivado separado. El baseline usa ese snapshot; Airflow sigue pendiente.

## Herramientas reproducibles con Docker

Desde Ubuntu, con Docker Desktop activo:

```bash
docker compose -f compose.tools.yaml build tools
docker compose -f compose.tools.yaml run --rm tools
docker compose -f compose.tools.yaml run --rm tools dvc repro snapshot_demo
docker compose -f compose.tools.yaml run --rm tools dvc status
```

El primer comando construye las herramientas con las versiones de `requirements/tools.lock`; el segundo ejecuta pytest. Los otros reconstruyen el snapshot y consultan DVC localmente, usando las entradas preparadas en la etapa anterior. Ver [ENTORNO_DVC.md](docs/ENTORNO_DVC.md) para reconstruirlas cuando no existen. El contenedor trabaja sin red y sin acceso al contenido de `.dvc/config.local`; la construcción sí necesita descargar la base y dependencias.

`scenario.dvc` e `ingestion.dvc` referencian entradas; `dvc.yaml` y `dvc.lock` describen la transformación y sus hashes. Se conserva el remoto Google Drive existente y todavía no se han enviado artefactos nuevos.

## Notebook

`analisis_exploratorio.ipynb` permanece intacto y está ignorado por Git. La copia `notebooks/analisis_exploratorio_revisado.ipynb` corrige el máximo por familia y se conserva sin salidas ni resultados de datos, lista para versionar. Requiere pandas y Jupyter, aún no preparados en WSL. No se ha ejecutado esa copia completa desde WSL.

## Primer baseline

```bash
docker compose -f compose.tools.yaml run --rm tools dvc repro baseline_predict
```

El baseline usa ventas recientes del mismo día de semana y genera cuantiles 0.1/0.5/0.9 por tienda/familia para siete días posteriores al corte. El [tutorial del baseline](docs/BASELINE.md) explica ventana, respaldo por historia insuficiente y artefactos. El modelo está en `models/baseline-demo/` y el pronóstico en `forecasts/baseline-demo/`, ambos bajo DVC y fuera de Git. Todavía no hay comparación temporal con ML ni pedidos basados en costos.

## Entorno verificado

WSL2 Ubuntu y Docker Desktop con motor Linux accesible. Las herramientas del contenedor usan Python 3.12; el Python del host continúa independiente. Comprobar desde la terminal:

```bash
docker version
docker compose version
docker info --format '{{.OSType}}'
```

Si vuelve a faltar la integración, abrir Docker Desktop y habilitar Ubuntu en Settings → Resources → WSL Integration. La `.venv` existente es de Windows: no se reutiliza desde WSL. El intento de `.venv-wsl` quedó incompleto por falta de `ensurepip`; no se debe dar por instalado. No se han cambiado dependencias de Windows.

El remoto DVC existente es Google Drive; no se ha probado una descarga desde WSL. Las credenciales permanecen en configuración local ignorada. Los hashes locales de los cinco CSV coinciden con `dataOriginal.dvc`. No hay remoto Git configurado todavía.

## Etapas siguientes

1. Completado: escenario conservador, carga histórica inicial, bandeja inmutable, registro y selección por corte; pruebas de retrasos/correcciones/replay.
2. Entorno de herramientas Linux y referencias DVC locales de entradas/procesados de demostración. Pendientes: validaciones entre fuentes, calendario de polling y publicación autorizada de artefactos nuevos al remoto.
3. Baseline de cuantiles implementado. Pendientes: ML y evaluación temporal idéntica, costos configurables y regla de sustitución.
4. Recomendaciones de abastecimiento y seguimiento de publicaciones.
5. Airflow 3, Compose, pytest/CI, documentación de reconstrucción y evidencias completas.
6. GitHub y protección mediante acciones autorizadas, revisión de aceptación y tag local de entrega.

Las instrucciones para reconstruir el producto completo se añadirán al implementar y verificar cada etapa. No existe aún evidencia de ejecución de Airflow ni de reproducción de pronósticos pasados.

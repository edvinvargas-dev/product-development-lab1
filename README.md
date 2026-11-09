# Laboratorio 1: motor de reposición

Estado: ingesta temporal, baseline/ML, comparación y mecanismo de objetivos de abastecimiento/costos con DVC local. Los costos activos están pendientes de definición. El producto completo y Airflow aún no están implementados. Decisiones y supuestos en [DECISIONES.md](DECISIONES.md); requisitos pendientes en [docs/ACEPTACION.md](docs/ACEPTACION.md).

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

El baseline usa ventas recientes del mismo día de semana y genera cuantiles 0.1/0.5/0.9 por tienda/familia para siete días posteriores al corte. El [tutorial del baseline](docs/BASELINE.md) explica ventana, respaldo por historia insuficiente y artefactos. El modelo está en `models/baseline-demo/` y el pronóstico en `forecasts/baseline-demo/`, ambos bajo DVC y fuera de Git. Ya hay comparación temporal con el candidato ML; los pedidos basados en costos siguen pendientes.

## Evaluación temporal de desarrollo

Con la nueva bandeja de evaluación preparada:

```bash
docker compose -f compose.tools.yaml run --rm tools dvc repro baseline_backtest
```

Se evalúan cuatro cortes semanales de julio con casos, snapshots y reales congelados. Los resultados por corte y globales se guardan en `data/evaluation/baseline-dev-v1/metrics.json`, bajo DVC. El [tutorial de evaluación](docs/EVALUACION_TEMPORAL.md) contiene la preparación desde cero y explica MAE, WAPE, pinball y cobertura. El contexto común de `data/evaluation/dev-context-v1/` se reutiliza en la evaluación ML; los reales posteriores al corte nunca se entregan a la función de ajuste.

## Primer ML y comparación

```bash
docker compose -f compose.tools.yaml build ml
docker compose -f compose.tools.yaml run --rm ml
docker compose -f compose.tools.yaml run --rm ml dvc repro model_comparison
```

La imagen `ml` añade cinco dependencias científicas sin actualizar las 117 de `tools`. Usar `ml` para ejecutar la suite completa, incluido el modelo. Se conservan los mismos casos del baseline. El candidato mantiene q50 y aprende q10/q90 con boosting; redujo el pinball medio un 5.1189 %, con MAE idéntico y cobertura de 64.2296 %.

Pasó el criterio técnico registrado antes de entrenar, pero no se promovió: faltan calibración suficiente, holdout y costos. Ver [MODELO_ML.md](docs/MODELO_ML.md) para diseño, variables, resultados por corte y reproducción de los modelos guardados. Los artefactos están en `data/evaluation/ml-dev-v1/` y `comparison-v1/`, bajo DVC local, fuera de Git.

## Objetivos de abastecimiento y costos

```bash
docker compose -f compose.tools.yaml run --rm ml dvc repro orders_configured orders_example business_example
```

`config/costs.json` conserva costos pendientes, sin inventar valores reales. El ejemplo separado `config/examples/costs-relative-9-1.json` permite revisar objetivos diarios y costo asimétrico ilustrativo. Hay costos por defecto y excepciones por familia; cambiar su relación cambia el cuantil elegido sin modificar código.

Las salidas tienen cantidad objetivo y stock desconocido; no se presenta un pedido neto de inventario. La [guía de pedidos y costos](docs/PEDIDOS_Y_COSTOS.md) explica fórmula, interpolación, límites y métrica de negocio proxy. Las salidas y la comparación ilustrativa están bajo `data/orders/` y `data/evaluation/business-example-9-1/`, versionadas con DVC. Falta definir qué costos/escenario se activarán y conectar publicaciones y seguimiento.

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
3. Baseline, ML y comparación bajo el mismo contexto implementados, con criterio técnico previo. Pendientes: calibración/holdout, costos configurables y evaluación de negocio para sustituir el modelo vigente.
4. Mecanismo de objetivos/costos y evaluación ilustrativa implementados. Pendientes: definición de costos activos, publicaciones inmutables y seguimiento operativo.
5. Airflow 3, Compose, pytest/CI, documentación de reconstrucción y evidencias completas.
6. GitHub y protección mediante acciones autorizadas, revisión de aceptación y tag local de entrega.

Las instrucciones para reconstruir el producto completo se añadirán al implementar y verificar cada etapa. No existe aún evidencia de ejecución de Airflow ni de reproducción de pronósticos pasados.

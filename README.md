# Laboratorio 1: motor de reposición de inventario

Producto de ML que, en cada fecha de corte y sin intervención manual, transforma las entregas diarias de datos de Corporación Favorita en:

1. **Pronóstico diario** por tienda y familia para los 7 días siguientes, con incertidumbre (cuantiles 0.1 / 0.5 / 0.9).
2. **Pedido sugerido** (objetivo diario de abastecimiento) derivado del pronóstico y de los costos de faltante y merma de [`config/costs.json`](config/costs.json). Si cambian los costos, cambia la recomendación sin tocar el código.
3. **Seguimiento del desempeño**: compara las publicaciones anteriores con las ventas reales a medida que se conocen, incluyendo las correcciones.

Usa Git, DVC y Apache Airflow 3, de modo que cada publicación se puede rastrear hasta el código, los datos y el modelo que la produjeron. Las decisiones y su justificación están en [DECISIONES.md](DECISIONES.md), y el estado frente al enunciado en [docs/ACEPTACION.md](docs/ACEPTACION.md).

## Levantar y ejecutar desde cero

Requisitos: Docker con Compose v2 (Docker Desktop en Windows o macOS, o Docker Engine en Linux), unos 4 GB de RAM libres y Git. No hace falta instalar Python.

```bash
git clone https://github.com/edvinvargas-dev/product-development-lab1.git laboratorio1 && cd laboratorio1
mkdir -p dataOriginal
# Copiar a dataOriginal/ los cinco CSV de Kaggle (store-sales-time-series-forecasting):
#   train.csv  stores.csv  holidays_events.csv  oil.csv  transactions.csv
# (test.csv y sample_submission.csv no se usan)
echo "AIRFLOW_UID=$(id -u)" > .env        # en Linux; en Windows/macOS basta copiar .env.example a .env
docker compose up -d
```

Abrir <http://localhost:8080>. La interfaz no pide usuario: el SimpleAuthManager está en modo local con todos como administradores. Si el puerto está ocupado, se cambia con `AIRFLOW_PORT=8081` en `.env`.

**No hay que hacer nada más.** Al levantar Compose:

1. `bandeja_simulada` (productor, `@once`) genera la bandeja inmutable desde `dataOriginal/` según [`config/operacion.json`](config/operacion.json). Tarda alrededor de 1–2 minutos.
2. `reposicion_diaria` (consumidor, `@daily`, `catchup=True`) espera a la bandeja y recorre cada día del periodo configurado, del 2017-08-01 al 2017-08-17, con estas tareas:

```
esperar_bandeja ─┐
resolver_corte ──┴─> ingesta_y_validacion_entregas -> preparacion_snapshot -> validacion_cruzada
                                                     -> pronostico_y_pedido -> seguimiento
```

Cada corte tarda alrededor de 1 minuto en una laptop. Las ejecuciones son secuenciales (`max_active_runs=1`).

### Salidas

| Ruta | Contenido |
|---|---|
| `data/scenarios/operacion-v1/inbox/` | Bandeja: un archivo por fuente, fecha y revisión, más `manifest.json`. Es externa e inmutable |
| `data/ingestion/operacion-v1.json` | Registro de ingesta: `receipts` con `ingested_at` y `rejections` (cuarentena) |
| `data/processed/operacion-v1/<día>/` | Snapshot de lo conocido en el corte, que es la entrada preparada para el modelo |
| `data/published/operacion-v1/<día>/<id>/` | **Publicación inmutable**: `forecast.csv`, `orders.csv`, `model.json`, `validation.json`, `manifest.json` y `provenance.json` (commit de Git) |
| `data/tracking/operacion-v1/<día>/report.md` | **Reporte de seguimiento** legible, junto con `tracking.json` |

### Periodo nuevo o no publicado

Para operar sobre otro periodo:
1. Colocar los CSV con ese periodo en `dataOriginal/`.
2. En `config/operacion.json`:
   - cambiar `scenario_id` y las seis rutas de `paths` que contienen `operacion-v1`;
   - ajustar `history_start` / `history_end` (carga histórica inicial) y `operation.start_date` / `end_date`. `delivery_end: "auto"` toma la última fecha de ventas disponible; también acepta una fecha;
   - **vaciar `delays` (`"delays": []`) o mover sus fechas dentro del nuevo rango.** Una demora fuera del rango detiene el productor con `ValueError: Demora fuera del escenario o para fuente estática`. En cambio, las `corrections` e `invalid_deliveries` fuera del rango se ignoran.
3. Levantar Airflow:
   - **Instalación nueva** (sin corridas previas): `docker compose up -d`. El productor y el consumidor corren solos.
   - **Instalación que ya corrió otro escenario:** `bandeja_simulada` es `@once` y no vuelve a ejecutarse con un reinicio. Hay que reiniciar los servicios para que el consumidor tome las fechas nuevas y lanzar el productor:
     ```bash
     docker compose restart
     docker compose exec airflow-scheduler airflow dags trigger bandeja_simulada
     ```
     Otra opción es empezar desde cero con `docker compose down -v && docker compose up -d`, que borra el historial de Airflow pero no los archivos de `data/`. La prueba registrada abajo usó una instalación nueva; la vía de `trigger` sobre una instalación existente no se ha ejecutado.

*Evidencia (2026-11-11):* desde un clon limpio de `main` (`3df246f`), con una instalación nueva y solo `config/operacion.json` modificado (escenario `operacion-junio-v1`, historia del 2017-04-01 al 05-31 y operación del **2017-06-01 al 06-07**, un periodo nunca publicado), `docker compose up -d` generó la bandeja (285 entregas) y publicó los 7 cortes en `success`, con seguimiento, sin intervención manual. Ver [docs/evidencia/periodo-junio-2017.md](docs/evidencia/periodo-junio-2017.md).

### Backfill y reprocesamiento

```bash
docker compose exec airflow-scheduler airflow backfill create --dag-id reposicion_diaria \
  --from-date 2017-08-03 --to-date 2017-08-05 --reprocess-behavior completed
```

- **Backfill:** reconstruye lo que se sabía en cada corte (por `ingested_at`), sin reingestar. Si nada cambió, verifica las publicaciones byte a byte y no crea publicaciones nuevas.
  - *Evidencia (2026-11-10):* backfill del 08-03 al 08-05. Los 3 cortes terminaron en `success`, la ingesta con `mode: backfill` y `new_deliveries: 0`, y el pronóstico con `already_published`. De 548 archivos de salida, 547 quedaron idénticos byte a byte.
  - *Limitación conocida:* el backfill reescribe `data/tracking/<escenario>/latest.json` con su propio corte, aunque sea anterior al último (DECISIONES 17). Para restaurarlo: `docker compose -f compose.tools.yaml run --rm tools dvc checkout --force operacion-seguimiento.dvc`.
- **Cambio de entradas:** si cambiaron el código, los costos o lo conocido, crea una publicación nueva y conserva la anterior.
- **Correcciones:** se reflejan automáticamente en el seguimiento de cortes posteriores, en el campo `corrections_applied`.

### Situaciones de operación simuladas (`config/operacion.json`)

| Situación | Qué hace el producto |
|---|---|
| Fuentes con distinta anticipación (ventas a 1 día, petróleo y transacciones a 2) | Solo usa lo disponible e ingerido antes del corte |
| Transacciones del 2017-08-03 con 2 días extra de retraso | Aviso, sin falla y sin imputar valores |
| Ventas del 2017-08-07 de la tienda 44 llegan al 40 % y se corrigen (r2) 3 días después | El pronóstico publicado no se reescribe; el seguimiento usa r2 al llegar |
| Petróleo del 2017-08-09 con un valor negativo (r2 válida 1 día después) | Cuarentena en `rejections`; no entra al modelo y no detiene el flujo |
| Días sin precio del petróleo, ventas cero y tiendas cerradas | Situaciones esperadas: solo avisos |
| Archivo de la bandeja alterado (hash distinto) | Falla de integridad: detiene la ejecución |

## Modelos, validación y criterio de sustitución

- **Baseline (vigente):** cuantiles empíricos por día de semana con las últimas 4 semanas ([docs/BASELINE.md](docs/BASELINE.md)).
- **ML (retador):** mantiene la mediana del baseline y aprende q10/q90 con `HistGradientBoostingRegressor` y pérdida de cuantiles, con 33 variables de las cinco fuentes ([docs/MODELO_ML.md](docs/MODELO_ML.md)).
- **Validación temporal idéntica:** 4 cortes semanales de julio de 2017, mismos 49,896 casos, sin fuga de información ([docs/EVALUACION_TEMPORAL.md](docs/EVALUACION_TEMPORAL.md)).

| Métrica (desarrollo, julio 2017) | Baseline | ML | Cambio |
|---|---:|---:|---:|
| Pinball medio | 22.27 | 21.13 | **−5.12 %** (mejor en 3 de 4 cortes) |
| MAE / WAPE de la mediana | 61.23 / 0.1287 | igual | igual por diseño |
| Cobertura del intervalo 80 % | 57.3 % | 64.2 % | más cerca del nominal |
| Costo proxy 9:1 (negocio) | — | — | **−10.45 %** |

**Criterio de sustitución** ([config/model-selection.json](config/model-selection.json), registrado antes de entrenar). Para pasar el corte técnico, el ML debe cumplir todo esto: pinball ≥ 5 % menor, mejor en ≥ 3 de 4 cortes, MAE sin aumento, cobertura no más lejos del 80 % y mismos casos completos. Para **reemplazar al vigente** debe cumplir además: holdout independiente, |cobertura − 0.80| ≤ 0.10 y costo de negocio no peor. Hoy el ML **pasa el corte técnico y gana en costo**, pero su cobertura (64 %) está fuera de la tolerancia y falta el holdout. Por eso el modelo vigente en Airflow sigue siendo el baseline, y el criterio no se rebajó después de ver los resultados (DECISIONES 12 y 16).

Reproducir la comparación (imagen `ml` con scikit-learn):

```bash
docker compose -f compose.tools.yaml build tools ml
docker compose -f compose.tools.yaml run --rm ml dvc repro model_comparison business_configured
```

## Costos

En `config/costs.json`, el faltante vale 9 y el exceso o merma vale 1, en unidades relativas. Eso implica el cuantil crítico 9/(9+1) = 0.9. Es un **supuesto académico**: los CSV no contienen costos, márgenes ni inventario (DECISIONES 15). Se pueden definir excepciones por familia con `family_overrides`. Como no hay inventario disponible, la salida es un objetivo diario (`target_quantity`) y `net_order_quantity` queda vacío. No se inventa stock ([docs/PEDIDOS_Y_COSTOS.md](docs/PEDIDOS_Y_COSTOS.md)).

## Versionado con DVC y reproducción de un pronóstico pasado

Git no guarda datos ni modelos. El remoto DVC configurado es Google Drive (`.dvc/config`). Hoy están versionados con DVC:
- originales (`dataOriginal.dvc`);
- bandeja, registro y escenario de evaluación de desarrollo (`scenario.dvc`, `ingestion.dvc`, `evaluation-scenario.dvc`);
- snapshots, modelos, pronósticos, evaluación y comparación de `dvc.yaml` / `dvc.lock`;
- salidas de la operación con Airflow, del corte 2017-08-01 al 2017-08-17:

| Archivo DVC | Ruta | Contenido |
|---|---|---|
| `operacion-bandeja.dvc` | `data/scenarios/operacion-v1/inbox` | Bandeja externa e inmutable (308 archivos) |
| `operacion-registro.dvc` | `data/ingestion/operacion-v1.json` | Registro de ingesta con `receipts` y `rejections` |
| `operacion-snapshots.dvc` | `data/processed/operacion-v1` | Snapshots por corte |
| `operacion-publicaciones.dvc` | `data/published/operacion-v1` | 17 publicaciones inmutables: modelo, pronóstico, pedido y procedencia |
| `operacion-seguimiento.dvc` | `data/tracking/operacion-v1` | Seguimiento por corte |

Estos archivos se generan con `docker compose -f compose.tools.yaml run --rm tools dvc add <ruta>`. El 2026-11-10 se enviaron al remoto con `dvc push` (174 archivos), y `dvc status -c` confirmó "Cache and remote 'storage' are in sync".

**Acceso al remoto desde WSL.** La imagen `tools` no tiene red, así que el push y el pull se hacen con un entorno local:

```bash
sudo apt install -y python3-venv
python3 -m venv .venv-wsl
.venv-wsl/bin/pip install "dvc[gdrive]==3.67.1" "dvc-gdrive==3.0.1" \
  "pyOpenSSL==24.2.1" "cryptography==43.0.3" "PyDrive2==1.21.3" "asyncssh==2.22.0"
.venv-wsl/bin/dvc remote modify --local storage gdrive_client_id '<CLIENT_ID>'
.venv-wsl/bin/dvc remote modify --local storage gdrive_client_secret '<CLIENT_SECRET>'
.venv-wsl/bin/python scripts/dvc_drive_lotes.py pull       # o: push, status -c
```

**Credenciales de Google Drive.** Google bloquea el cliente OAuth que DVC trae por defecto ("Se bloqueó esta app"). Por eso cada usuario necesita:
- un cliente OAuth propio (Google Cloud Console → APIs y servicios → Credenciales, tipo *App de escritorio*, con la API de Drive habilitada), o los valores que el responsable del proyecto entregue por un canal privado;
- acceso compartido a la carpeta de Drive del remoto.

Los valores van solo en `.dvc/config.local`, que Git ignora; nunca se versionan. La primera ejecución abre el navegador para iniciar sesión.

Las versiones de `pyOpenSSL` y `cryptography` se fijan igual que en `requirements/tools.lock`. Si pip elige otras, DVC falla con `module 'lib' has no attribute 'GEN_EMAIL'`.

`scripts/dvc_drive_lotes.py` ejecuta DVC dividiendo en lotes las consultas a Google Drive. PyDrive2 1.21.3 arma una sola consulta con todas las carpetas del remoto (unas 190, más de 9 KB), y Drive la rechaza con `400 Bad Request`. El script no modifica los paquetes instalados.

Reproducir una publicación pasada a partir de su versión de código y de datos:

```bash
git checkout <commit-de-la-publicacion>   # versión del código (está en provenance.json)
dvc pull                                  # versión de los datos (requiere acceso al remoto)
docker compose -f compose.tools.yaml run --rm tools python -m src.operation reproduce --day 2017-08-05
```

`reproduce` reconstruye el snapshot del corte desde la bandeja y el registro versionados. Después reajusta el modelo, vuelve a pronosticar y a calcular el pedido en `data/reproduction/`, y compara cada archivo con la publicación original. Si todo coincide, termina con código 0.

**Evidencia (2026-11-10, copia local):** se reprodujo la publicación `751908fb5128` del corte 2017-08-05. Los cinco archivos (`forecast.csv`, `orders.csv`, `model.json`, `validation.json` y `manifest.json`) son idénticos byte a byte (`"identical": true`, código de salida 0). Por ejemplo, `forecast.csv` tiene SHA-256 `e7d86b57…cdee20`.

**Evidencia desde un clon limpio (2026-11-10):** se clonó `main` (`4e2eec9`) desde GitHub y se ejecutó `dvc pull` de `operacion-bandeja.dvc`, `operacion-registro.dvc` y `operacion-publicaciones.dvc` desde Google Drive. Después se corrió `reproduce --day 2017-08-05` en el contenedor `tools`. Resultado: `identical: true` en los cinco archivos, con los mismos SHA-256. El código de `src/` y `config/` en `main` es idéntico al del commit de la publicación (`ddb8e1d`).

## Pruebas y CI

```bash
docker compose -f compose.tools.yaml build tools
docker compose -f compose.tools.yaml run --rm tools          # pytest
python3 -m unittest discover -s tests -v                      # sin dependencias (WSL o Linux)
```

GitHub Actions ([.github/workflows/pruebas.yml](.github/workflows/pruebas.yml)) ejecuta pytest en cada Pull Request, incluidas las pruebas del ML. Todas usan datos sintéticos. **Pendiente:** verificar el workflow en GitHub y proteger `main`, para que los cambios entren solo por PR con las pruebas aprobadas.

## Estructura

```
config/     operacion.json, baseline.json, costs.json, ml.json, model-selection.json, ...
dags/       bandeja_simulada.py (productor), reposicion_diaria.py (consumidor): solo orquestan
src/        operation.py (pasos por corte), simulate.py, ingest.py, snapshot.py, validate_snapshot.py,
            baseline.py, ml.py, orders.py, tracking.py, metrics.py, evaluation.py, ...
tests/      pruebas con datos sintéticos (ingesta, correcciones, idempotencia, modelos, pedidos, operación)
docs/       tutoriales y aceptación;  docker/  imágenes de herramientas y ML
docker-compose.yaml  Airflow 3.3.2 + PostgreSQL;  compose.tools.yaml  herramientas DVC/pytest/ML
```

## Recorridos de desarrollo anteriores

Estos recorridos siguen disponibles y se documentan en sus tutoriales:
- auditoría de originales (`python3 -m src.audit`);
- ingesta temporal de demostración ([docs/INGESTA_TEMPORAL.md](docs/INGESTA_TEMPORAL.md));
- entorno DVC local ([docs/ENTORNO_DVC.md](docs/ENTORNO_DVC.md));
- notebook revisado (`notebooks/analisis_exploratorio_revisado.ipynb`).

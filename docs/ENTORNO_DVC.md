# Etapa 3: herramientas Linux y versionado local

## Para qué sirve esta etapa

La imagen de herramientas ejecuta Python, pytest y DVC en Linux. No depende de la `.venv` de Windows ni de instalar paquetes en Ubuntu. Airflow tendrá su propia configuración en una etapa posterior.

La base oficial de Python 3.12 está fijada por digest en `docker/tools.Dockerfile`. `requirements/tools.in` documenta las dependencias directas y las versiones de compatibilidad conocidas para Google Drive. `requirements/tools.lock` congela también las dependencias transitivas. No actualizar estos archivos de forma automática al ejecutar el producto.

La fijación cubre la base y los paquetes Python; la construcción instala Git desde los repositorios Debian. No se promete una imagen binariamente idéntica entre fechas de construcción, pero sí se verifica el conjunto instalado de paquetes Python.

## Construir y probar desde WSL Ubuntu

Ejecutar desde la raíz del proyecto, con Docker Desktop activo y su integración con Ubuntu habilitada:

```bash
docker compose -f compose.tools.yaml build tools
docker compose -f compose.tools.yaml run --rm tools
docker compose -f compose.tools.yaml run --rm tools python -m pip check
docker compose -f compose.tools.yaml run --rm tools dvc version
```

El comando sin argumentos ejecuta pytest. Los paquetes solo se descargan durante la construcción; los contenedores de trabajo tienen `network_mode: none`.

El contexto Docker contiene solo el Dockerfile y los requisitos, según `.dockerignore`. No se copian datos ni credenciales a las capas de la imagen. El código se monta al ejecutar. Los originales y `.git` se montan de solo lectura; `.dvc/config.local` se oculta con un montaje vacío de solo lectura. No es necesario autenticarse en Google Drive para las operaciones locales de esta etapa.

Esta configuración usa montajes Linux como `/dev/null`; ejecutar Compose desde Ubuntu, no desde PowerShell. La imagen usa UID 1000, que coincide con el usuario verificado en este workspace. En otro equipo Linux puede requerir adaptar el usuario del contenedor a los permisos del directorio.

## Qué versiona DVC ahora

| Referencia | Contenido | Función |
| --- | --- | --- |
| `dataOriginal.dvc` | Los cinco originales | Referencia existente, conservada |
| `scenario.dvc` | Bandeja de demostración y manifiesto | Entrada congelada; no se regenera desde el consumidor |
| `ingestion.dvc` | Registro de ingesta de la demostración | Estado de conocimiento con sus horas lógicas |
| `dvc.yaml` / `dvc.lock` | Snapshot del corte 2017-08-01 a las 13:00 UTC | Proceso y hashes para reconstruir datos conocidos |

Los CSV y el registro permanecen bajo `data/`, ignorados por Git. Solo las referencias, el código, la configuración y los archivos de bloqueo son candidatos para Git. El caché DVC sigue siendo local; no se ejecuta `dvc push` ni se cambia el remoto.

Una entrada `.dvc` sin comando representa datos externos. La etapa `snapshot_demo` lee esas entradas y genera una salida nueva en `data/processed/dvc-demo/2017-08-01`. No escribe en la bandeja ni sustituye los snapshots de la etapa anterior.

## Ejecutar y consultar

Con las entradas ya presentes y versionadas:

```bash
docker compose -f compose.tools.yaml run --rm tools dvc repro snapshot_demo
docker compose -f compose.tools.yaml run --rm tools dvc status
docker compose -f compose.tools.yaml run --rm tools dvc dag
```

`dvc repro` usa las dependencias declaradas en `dvc.yaml`. Si no cambiaron, omite el trabajo; si cambian, reconstruye el resultado. La regla de DVC es eliminar sus salidas antes de volver a ejecutar una etapa, salvo que se marque persistencia. Por eso esta etapa usa un directorio derivado nuevo, separado de la bandeja y de las publicaciones. Véase la [documentación oficial de repro](https://doc.dvc.org/command-reference/repro).

`dvc status` sin opciones de nube consulta el estado local. No debe confundirse con verificar que Google Drive tenga todas las versiones. El [registro de datos con DVC](https://doc.dvc.org/command-reference/add) guarda contenido en caché y referencias pequeñas; enviar ese caché al remoto es una acción distinta.

## Reconstrucción sin descargar de Google Drive

Si los originales están disponibles pero la bandeja y el registro no existen, se puede reconstruir la demostración:

```bash
docker compose -f compose.tools.yaml run --rm tools python -m src.simulate
docker compose -f compose.tools.yaml run --rm tools python -m src.ingest --at 2017-08-01T13:00:00Z
docker compose -f compose.tools.yaml run --rm tools python -m src.ingest --at 2017-08-05T13:00:00Z
docker compose -f compose.tools.yaml run --rm tools python -m src.ingest --at 2017-08-06T13:00:00Z
```

Es el calendario de polling usado en la evidencia. El productor rechaza un destino existente y el registro no puede retroceder: no repetir estos comandos de inicialización sobre una demostración que ya avanzó. En ese caso, usar las entradas existentes y ejecutar `dvc repro`, o elegir un escenario/directorio independiente como explica `INGESTA_TEMPORAL.md`.

La hora real `recorded_at_wall` será diferente al generar otro registro; sus bytes y hash DVC serán una nueva versión. Con las mismas horas lógicas y datos, el snapshot debe ser idéntico. Para una reproducción exacta del registro original hará falta recuperarlo de la caché o de su versión remota cuando se autorice su publicación.

Si se generaron entradas nuevas deliberadamente, registrar esa versión local antes de reconstruir:

```bash
docker compose -f compose.tools.yaml run --rm tools dvc commit --force scenario.dvc ingestion.dvc
docker compose -f compose.tools.yaml run --rm tools dvc repro snapshot_demo
```

`dvc commit` actualiza las referencias y guarda el contenido en el caché local; no crea un commit Git ni sube archivos. Usarlo solo para entradas nuevas conocidas, no para ocultar cambios inesperados.

## Límites

Todavía faltan modelos, pronósticos y sus referencias DVC. El replay demostrado aquí es de datos preparados, no de un pronóstico publicado. La configuración de Google Drive se conserva, pero su acceso desde Linux y la publicación de los artefactos nuevos siguen pendientes de autorización.

El punto de control de código y referencias de ingesta/DVC/baseline se registra en la rama local `feature/baseline-cuantiles`. La publicación y revisión remota siguen pendientes. No existe aún un tag de entrega ni evidencia final del laboratorio.

## Evidencia ejecutable de esta etapa

Con el snapshot de la etapa 2 en `data/processed/demo/2017-08-01`, ejecutar:

```bash
docker compose -f compose.tools.yaml run --rm tools python scripts/verify_local_dvc.py
```

Si falta ese snapshot de referencia, reconstruirlo con el comando de `src.snapshot` del tutorial anterior antes de ejecutar la verificación.

El script compara los seis archivos con la etapa anterior, retira temporalmente solo la salida derivada nueva, la restaura con `dvc checkout dvc.yaml:snapshot_demo` y fuerza un recálculo sin caché de ejecución. Guarda una copia previa bajo `data/verification/` y verifica igualdad de hashes, entradas intactas, estabilidad de `dvc.lock` y estado local actualizado. No usa checkout global ni retira los originales.

Evidencia generada: `reports/generated/dvc_local_replay.json`. Se verificaron restauración y recálculo idénticos. `dvc status --json` devolvió `{}`. Las 14 pruebas pasaron con pytest y la imagen se construyó también usando las 117 versiones transitivas bloqueadas. La comprobación de versiones y pruebas de la imagen final se registra en `reports/generated/environment_verified.json`.

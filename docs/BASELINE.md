# Etapa 4: primer pronóstico con incertidumbre

## Qué calcula

El baseline usa las ventas conocidas de cada tienda y familia en los 28 días anteriores a la fecha de emisión. Para un miércoles, consulta miércoles anteriores. Con al menos tres observaciones de ese día de semana, calcula cuantiles empíricos 0.1, 0.5 y 0.9 mediante interpolación lineal sobre la muestra ordenada.

El cuantil 0.5 es la mediana. Los cuantiles 0.1 y 0.9 describen la dispersión de esa muestra. Todavía no están calibrados: no se garantiza cobertura del 80 % en ventas futuras. La muestra de demostración tiene solo cuatro observaciones de cada día de semana por serie.

Si hay pocas observaciones del día de semana, usa todos los días de esa misma tienda/familia en la ventana, siempre que haya al menos siete. Si tampoco alcanza, entrega `insufficient_history` con predicción vacía. Una observación real de venta cero se conserva como cero; ausencia de historia no se transforma en cero.

Las reglas están en `config/baseline.json`. Estos parámetros son técnicos; no representan costos de faltante/merma ni inventario. El baseline todavía no calcula pedidos.

## Qué datos puede ver

El único punto de entrada es el snapshot del corte, no `dataOriginal/train.csv`. Se comprueban sus hashes, entregas seleccionadas, horas de disponibilidad/ingesta, claves y fechas. Con el contrato conservador actual, las fechas observadas deben preceder al día del corte.

El snapshot contiene las cinco fuentes. En esta etapa se usan para validación y contexto; el baseline numérico usa únicamente ventas y calendario. El futuro ML deberá incorporar covariables conocidas sin mirar valores futuros.

Ventas y transacciones deben referenciar tiendas del catálogo estático completo de este escenario. Una tienda desconocida, un duplicado, un número inválido o un hash alterado detienen el proceso. Si no se conocen aún el catálogo o las ventas, se entrega estado `not_ready`, sin inventar un modelo.

Fechas sin transacciones/precios, precios vacíos y cobertura incompleta se informan separadamente. No se borran ceros/extremos ni se interpolan datos usando el futuro. El informe de validación indica faltantes, no prueba por sí solo su causa de negocio.

## Cómo ejecutarlo

Con las entradas de la demostración presentes y el entorno de herramientas construido:

```bash
docker compose -f compose.tools.yaml run --rm tools
docker compose -f compose.tools.yaml run --rm tools dvc repro baseline_predict
docker compose -f compose.tools.yaml run --rm tools dvc status
```

DVC ejecuta las dependencias en orden: snapshot → ajuste del baseline → predicción. Se crearon dos etapas nuevas en `dvc.yaml`, con sus hashes en `dvc.lock`.

Para consultar la validación de forma independiente:

```bash
docker compose -f compose.tools.yaml run --rm tools python -m src.validate_snapshot --snapshot data/processed/dvc-demo/2017-08-01
```

## Artefactos locales

| Ruta | Contenido |
| --- | --- |
| `models/baseline-demo/model.json` | Cuantiles por serie/día de semana, parámetros, fechas de ajuste e identificador de contenido |
| `models/baseline-demo/validation.json` | Resultado de validaciones conjuntas y advertencias de disponibilidad |
| `models/baseline-demo/status.json` | Disponibilidad de insumos para ajustar |
| `forecasts/baseline-demo/forecast.csv` | Pronóstico en formato largo: una fila por fecha/tienda/familia/cuantil |
| `forecasts/baseline-demo/manifest.json` | Corte, horizonte, identificador/hash del modelo y hash del pronóstico |

Todos estos archivos están excluidos de Git y versionados localmente con DVC. Las funciones de publicación rechazan sobrescrituras diferentes cuando se invocan directamente. Las rutas `baseline-demo` son salidas derivadas reconstruibles de la demostración: DVC puede sustituirlas al recalcular. No son todavía el registro operativo inmutable de publicaciones; ese registro se construirá antes de seguimiento/despliegue.

El identificador del modelo se calcula a partir de su contenido, configuración y referencia al snapshot. No depende de la hora real en que se ejecuta el programa.

## Resultado de demostración

Se emitió con corte `2017-08-01T13:00:00Z`. La ventana de ajuste es 2017-07-04 a 2017-07-31: 49,896 observaciones para 1,782 series. Los objetivos son los siete días posteriores al día del corte, 2017-08-02 a 2017-08-08. Se decidió excluir el propio día del corte porque este ocurre a las 13:00 UTC; no se presenta una venta diaria parcialmente transcurrida como un objetivo futuro completo.

El archivo contiene 37,422 filas: 54 tiendas × 33 familias × 7 días × 3 cuantiles. El horizonte de siete días sigue siendo una decisión provisional de producto; esta ejecución permite probarlo.

En el snapshot había 54 tienda/fecha con ventas sin transacciones conocidas, 11 fechas de ventas sin fila de petróleo y dos precios vacíos. Se conservaron y reportaron, sin hacer fallar esta ejecución por esas ausencias esperables.

## Qué falta para comparar modelos

Las 23 pruebas automatizadas comprueban cuantiles conocidos, prioridad del mismo día de semana, ventana temporal, ceros, falta de historia, exclusión de futuros, integridad y reintentos, además de los casos previos de ingesta/auditoría. Esto valida el funcionamiento; no demuestra calidad predictiva.

Falta evaluar este baseline y el ML con exactamente los mismos cortes temporales, medir errores/cobertura y aplicar costos configurables cuando se definan. No se han usado las ventas reales del horizonte para ajustar estos cuantiles ni se ha declarado un modelo ganador.

## Reproducibilidad comprobada

Se forzó un recálculo con `dvc repro --force --no-run-cache baseline_predict` y se compararon los hashes del modelo, pronóstico y manifiesto: idénticos. Se verificaron los 12,474 grupos fecha/tienda/familia con sus tres cuantiles ordenados y no negativos. No hubo filas sin historia suficiente en esta demostración. Resumen de evidencia en `reports/generated/baseline_verified.json`, fuera de Git.

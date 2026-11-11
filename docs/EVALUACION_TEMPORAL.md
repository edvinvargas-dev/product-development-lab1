# Etapa 5: evaluar un pronóstico con información de su época

## El experimento

Se congeló `config/evaluation.json` antes de consultar las métricas. Define cuatro cortes de desarrollo, un horizonte de siete días, cuantiles 0.1/0.5/0.9 y un cierre de evaluación fijo. No hay división aleatoria de filas.

| Corte a las 13:00 UTC | Ventana prevista de ajuste del baseline | Fechas objetivo |
| --- | --- | --- |
| 2017-07-04 | 2017-06-06 a 2017-07-03 | 2017-07-05 a 2017-07-11 |
| 2017-07-11 | 2017-06-13 a 2017-07-10 | 2017-07-12 a 2017-07-18 |
| 2017-07-18 | 2017-06-20 a 2017-07-17 | 2017-07-19 a 2017-07-25 |
| 2017-07-25 | 2017-06-27 a 2017-07-24 | 2017-07-26 a 2017-08-01 |

Las ventanas de entrenamiento avanzan con el tiempo y los horizontes objetivo no se solapan. Una fecha de una evaluación anterior puede ser historia conocida en un corte posterior; es lo que ocurriría en operación. Solo se admite cuando ya estaba disponible e ingerida.

Las ventas reales se consultan con conocimiento hasta `2017-08-03T13:00:00Z`. Ese cierre determina qué revisión del real puede usarse para puntuar. Un real pendiente no es una venta cero; se informa por separado.

Este bloque es de desarrollo. Las ventas posteriores al 1 de agosto no se puntúan aquí. No constituye una estimación final sobre el período desconocido que usará el equipo docente.

## Bandeja independiente y calendario simulado

`config/evaluation-simulation.json` prepara una bandeja nueva con historia desde el 1 de junio y entregas hasta el 1 de agosto. Tiene 249 entregas más el manifiesto. Conserva los mismos retrasos base conservadores y agrega dos días de demora a transacciones del 10 de julio. Son supuestos simulados, no horarios observados de Favorita; no se modifican ventas.

El primer polling ocurre el 4 de julio a las 13:00 UTC e incorpora la historia elegible. Luego hay un polling diario hasta el cierre. Las fuentes futuras quedan pendientes y se incorporan cuando corresponda. La bandeja de la demostración anterior permanece intacta.

La preparación usa `src.replay` para calcular el primer polling elegible de cada entrega de esta bandeja fija, validándola una sola vez. Guarda un `logical_ledger.json` con disponibilidad e ingesta simuladas, sin inventar una hora real de ingesta. Es equivalente al polling operativo sobre el mismo escenario congelado, pero evita releer todos los archivos cada día. Las pruebas comparan ambos registros exactamente. El registro operativo de la demostración anterior y su auditoría real no se modifican. Esta separación evita que ejecutar el mismo experimento hoy o mañana cambie los datos reproducidos.

## Un mismo contexto para baseline y ML

La etapa `evaluation_context` congela los snapshots de cada corte, su validación, la lista de casos a predecir, el calendario de polling y el snapshot de reales al cierre.

Cada lista `cases.csv` se construye con las tiendas y familias conocidas en el corte, sin mirar qué ventas tendrán éxito o error después. Su hash y el del contexto identifican el conjunto común de comparación. Si un modelo omite una predicción, el caso sigue contando como no disponible. No se permite que mejore su resultado simplemente descartando casos difíciles.

El ajuste del modelo recibe exclusivamente el snapshot del corte. El módulo de puntuación recibe después el pronóstico y los reales. Una prueba sintética demuestra que corregir un real del horizonte después de la emisión cambia la métrica sin cambiar el identificador del modelo anterior.

El futuro ML deberá usar exactamente estos casos, cortes, horizonte, cuantiles y reales. También se debe comprobar la misma completitud antes de declarar una mejora; una métrica calculada sobre subconjuntos diferentes no basta.

## Qué mide cada número

| Métrica | Interpretación |
| --- | --- |
| MAE | Promedio del error absoluto de la mediana, en unidades de ventas |
| RMSE | Error de la mediana que da mayor peso a errores grandes |
| Sesgo | Predicción mediana menos real; negativo indica subestimación promedio |
| WAPE | Suma de errores absolutos dividida por suma de ventas reales; multiplicar por 100 para porcentaje |
| Pinball por cuantil | Penaliza errores según el cuantil; distingue subestimación de sobreestimación |
| Pinball medio | Promedio entre los cuantiles y casos puntuados; menor es mejor |
| Cobertura del intervalo | Fracción de reales entre q10 y q90, incluyendo los extremos |
| Ancho del intervalo | Promedio de q90 menos q10; ayuda a interpretar la cobertura |

La cobertura nominal q10–q90 es 80 %, pero el baseline no garantiza alcanzarla. Un intervalo más ancho puede cubrir más casos: se necesita mirar cobertura, ancho y pinball conjuntamente.

Se reportan casos esperados, puntuados, reales pendientes y pronósticos no disponibles. Con denominador de ventas cero, WAPE es `null`, sin reemplazar el denominador con una constante. Sin casos puntuados, las métricas son `null`.

Las métricas globales agrupan casos puntuados, sin promediar promedios de cortes. MAE/pinball agregan familias con distintas escalas y unidades; no son costos monetarios. La comparación entre modelos debe conservar las mismas series, y se podrá ampliar el desglose por familia. La métrica de negocio queda explícitamente pendiente porque todavía no hay costos configurados.

## Ejecutar desde cero

Con los cinco originales y la imagen de herramientas disponibles:

```bash
docker compose -f compose.tools.yaml run --rm tools python -m src.simulate --config config/evaluation-simulation.json --output data/scenarios/evaluacion-julio-v1/inbox
docker compose -f compose.tools.yaml run --rm tools dvc commit --force evaluation-scenario.dvc
docker compose -f compose.tools.yaml run --rm tools dvc repro baseline_backtest
```

El primer comando se usa solo para preparar una bandeja inexistente. Si ya existe, el generador la protege y se detiene; no hay que borrarla. `dvc commit` registra esa entrada conocida en caché local, sin crear un commit Git ni subir datos.

Con el experimento ya preparado, basta repetir:

```bash
docker compose -f compose.tools.yaml run --rm tools
docker compose -f compose.tools.yaml run --rm tools dvc repro baseline_backtest
docker compose -f compose.tools.yaml run --rm tools dvc status
```

## Artefactos

- `evaluation-scenario.dvc`: referencia local de la nueva bandeja externa.
- `data/evaluation/dev-context-v1/`: contexto común, casos, snapshots de entrenamiento y reales, registro lógico y manifiesto con hashes.
- `data/evaluation/baseline-dev-v1/metrics.json`: métricas por corte y globales, completitud y estado de costos.
- `data/evaluation/baseline-dev-v1/folds/<fecha>/`: modelo, pronóstico, unión con reales y métricas de cada emisión simulada.

Contexto y resultados están versionados localmente con DVC y excluidos de Git. Son artefactos de evaluación de desarrollo, separados de la futura publicación operativa inmutable. El consumidor nunca modifica la bandeja. No se cambió el remoto ni se enviaron datos.

## Límites y siguiente paso

Todavía no hay ML, costos/pedidos, comparación de negocio ni promoción de modelo. Primero se examina el comportamiento de este piso de comparación; después se implementará el candidato ML bajo este mismo contexto y se definirá el criterio de sustitución antes de comparar candidatos. Airflow, seguimiento operativo y evidencia final del laboratorio siguen pendientes.

## Rendimiento del replay

La primera ejecución real validaba repetidamente entregas ya conocidas al simular cada día. Se añadió un replay específico para escenarios congelados, sin cambiar `src.ingest`: selecciona el primer polling posterior o igual a `available_at`, y deja pendientes los archivos ausentes. No lee valores de entregas posteriores al cierre.

Antes de sustituir el recorrido se compararon las 175 entregas de los primeros 12 pollings reales: registro lógico idéntico. Las pruebas sintéticas cubren también demoras, correcciones, archivos ausentes y datos futuros. La referencia parcial interrumpida se conservó bajo `reports/generated/reference-replay-interrupted/`; el resumen de equivalencia está en `reports/generated/replay_equivalence.json`. Estos archivos auxiliares no son entradas del experimento.

Este replay no es un consumidor de un origen que cambia físicamente mientras se ejecuta: requiere la bandeja congelada y su contrato de disponibilidad. Para operación se mantiene la ingesta con su registro de observación real/simulada, según corresponda.

## Resultados ejecutados

Se puntuaron los 49,896 casos esperados, 12,474 por corte, sin reales pendientes ni pronósticos faltantes. Se generaron 149,688 predicciones individuales de cuantil. No se cambió la configuración del baseline después de observar sus métricas.

| Corte | MAE | WAPE | Cobertura q10–q90 | Pinball medio |
| --- | ---: | ---: | ---: | ---: |
| 4 de julio | 56.9931 | 11.8801 % | 59.7884 % | 20.2118 |
| 11 de julio | 54.6886 | 11.8388 % | 58.5378 % | 19.5597 |
| 18 de julio | 58.5808 | 12.7617 % | 55.0585 % | 21.5077 |
| 25 de julio | 74.6487 | 14.8605 % | 55.9003 % | 27.8157 |
| Global por casos | 61.2278 | 12.8694 % | 57.3212 % | 22.2737 |

RMSE global: 235.3317; sesgo de la mediana: -5.9051; ancho medio del intervalo: 118.6359. Son métricas de este bloque de desarrollo, no costos monetarios ni estimaciones garantizadas para otro período.

La cobertura queda por debajo del 80 % nominal en los cuatro cortes: el intervalo empírico no está bien calibrado en este bloque. El último corte tiene mayor error. Se conserva como parte de la evaluación, sin eliminar valores extremos ni escoger únicamente semanas favorables. Esto establece el piso de comparación para el candidato ML; no demuestra aún una mejora de otro modelo.

Pasaron 37 pruebas con pytest en Linux. Para verificar restauración y recálculo de los resultados completos:

```bash
docker compose -f compose.tools.yaml run --rm tools python -m scripts.verify_evaluation
```

El script conserva una copia previa, restaura solo la salida de `baseline_backtest` desde el caché DVC y recalcula sobre el mismo contexto, comprobando hashes y contexto intacto. Guarda evidencia local en `reports/generated/evaluation_verified.json`; no requiere red ni credenciales.

## Recuperación de una interrupción durante el desarrollo

Al detener la ejecución lenta de referencia quedó un registro de bloqueo en `.dvc/tmp/rwlock` que atribuía dependencias al PID 7 del contenedor cancelado. Esto afectó a `dvc status` en la primera verificación, después de que restauración y recálculo ya hubieran coincidido.

Se comprobó que no había contenedores activos del proyecto de herramientas y que todos los propietarios del bloqueo correspondían exactamente a ese comando interrumpido. Se conservó el archivo como `.dvc/tmp/rwlock.interrupted-evaluation.bak`, sin borrar datos ni caché, y se repitió la verificación. No se añadió limpieza automática de bloqueos al producto: nunca se debe retirar un bloqueo sin comprobar que su propietario ya terminó.

La verificación final completó restauración y recálculo idénticos; el contexto no cambió y `dvc status --json` devolvió `{}`. Los originales y la demostración anterior se verificaron intactos por hash. Esta evidencia sigue siendo local; faltan publicación autorizada en el remoto y registro operativo de pronósticos.

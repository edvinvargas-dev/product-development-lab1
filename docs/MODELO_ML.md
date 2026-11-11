# Etapa 6: ML para la incertidumbre del pronóstico

## Lo fijado antes de entrenar

El commit `2f765f6` registró `config/ml.json`, `config/model-selection.json` y `docs/PLAN_ML.md` antes de consultar resultados del candidato. Se conservan los cuatro cortes de julio, los casos y los reales congelados de la etapa anterior.

El candidato es híbrido: q50 sigue siendo la mediana del baseline; q10 y q90 se aprenden con regresores de boosting de histogramas y pérdida de cuantiles. No se afirma que se haya aprendido una nueva mediana ni mejorado su MAE. La mejora buscada está en la incertidumbre, que mostró cobertura insuficiente en el baseline.

La [documentación de scikit-learn 1.7.2](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) describe la pérdida de cuantiles y el soporte para categorías y faltantes. Se usan dos regresores, uno por extremo, con parámetros fijos y sin validación aleatoria interna.

## Qué aprende

Para cada ejemplo histórico:

```text
residuo = (venta_real - mediana_baseline) / escala
pronóstico_q = mediana_baseline + escala × modelo_q(variables)
```

La escala usa la mediana y el promedio reciente, con un mínimo numérico configurable para series con muchos ceros. El peso de cada ejemplo es su escala: la pérdida normalizada ponderada conserva la relación con pinball en unidades de ventas. Las observaciones cero y extremas se mantienen.

Los límites de salida se proyectan a ventas no negativas y al orden q10 ≤ q50 ≤ q90. La mediana permanece fija. No se utilizan los reales del horizonte evaluado para ampliar intervalos después de medirlos.

## Variables y disponibilidad

| Fuente | Variables usadas |
| --- | --- |
| train | Familia y ventas anteriores: último valor, medias, variación, estadísticas del mismo día de semana, cantidad de observaciones; promociones anteriores |
| stores | Tienda y categorías del catálogo estático: ciudad, estado, tipo y cluster |
| transactions | Últimas transacciones conocidas, media reciente, cantidad de observaciones y antigüedad |
| oil | Último precio no vacío conocido y su antigüedad |
| holidays_events | Eventos anteriores aplicables a la tienda y cantidad de días con entrega de calendario conocida |
| Calendario calculado | Horizonte, día de semana, día/mes, fin de mes e indicador del día 15 o último día |

El indicador del día 15/fin de mes es una hipótesis de calendario calculable, no un registro observado de pagos. Las categorías de tiendas conservan el supuesto estático documentado en el escenario.

No se consultan promociones, petróleo, transacciones ni feriados futuros del CSV. Un valor de petróleo vacío no pasa a ser cero: se usa un precio anterior conocido, con antigüedad explícita, o faltante si no existe. Sin transacciones conocidas se conserva faltante junto con cantidad cero de observaciones; eso no equivale a transacciones reales cero. Los eventos transferidos no se cuentan como evento efectivo en su fecha original.

## Ejemplos históricos sin fuga

Cada ejemplo tiene un origen y un objetivo posterior. Las características solo usan días anteriores al origen y entregas disponibles en la fuente antes de ese instante. La etiqueta debe estar disponible en el snapshot del ajuste. Una corrección seleccionada posterior al origen histórico se excluye de sus características, en vez de retrotraer su valor.

El entrenamiento reconstruye ejemplos históricos a partir de la carga inicial: usa disponibilidad simulada en el origen, sin inventar ingestas operativas anteriores al despliegue. En el corte de pronóstico evaluado también se exige que todos los datos hayan sido ingeridos antes de emitir, como comprueba el snapshot.

Se toman orígenes históricos cada tres días dentro de la ventana de entrenamiento configurada. Esta frecuencia solo reduce el tamaño de entrenamiento; los cuatro cortes y todos los casos de evaluación permanecen iguales. `training_index.csv` registra origen, objetivo, etiqueta, disponibilidad de etiqueta y máxima disponibilidad usada por las variables.

## Entorno aislado

`ml` es un servicio adicional de `compose.tools.yaml`, basado en la imagen existente de herramientas. Añade NumPy 2.3.3, SciPy 1.16.2, scikit-learn 1.7.2, joblib 1.5.2 y threadpoolctl 3.6.0. Los 117 paquetes originales siguen con sus mismas versiones; el entorno completo verificado tiene 122. Sus requisitos están en `docker/ml/requirements.lock`, restringidos por `requirements/tools.lock`.

La [dependencia de construcción entre servicios de Compose](https://docs.docker.com/reference/compose-file/build/#additional_contexts) permite reutilizar la base sin publicarla. El contexto nuevo contiene solo Dockerfile y requisitos. El runtime hereda ausencia de red, originales de solo lectura y ocultación de credenciales. No se cambia la `.venv` de Windows ni se instala software en Ubuntu.

Se usa un hilo y semilla fija. El modelo guardado incluye versiones, esquema de características, mapas categóricos, hash del snapshot, fingerprint de los datos de entrenamiento e identificador de contenido. El binario se carga solo desde artefactos propios confiables de DVC, comprobando hash y versiones antes de deserializarlo.

## Ejecutar

Con la evaluación de desarrollo ya preparada:

```bash
docker compose -f compose.tools.yaml build ml
docker compose -f compose.tools.yaml run --rm ml
docker compose -f compose.tools.yaml run --rm ml dvc repro model_comparison
```

El primer comando construye el entorno nuevo. El segundo ejecuta la suite completa, incluido entrenamiento sintético, guardado/carga y determinismo. El tercero reutiliza el contexto y baseline congelados, entrena ML y ejecuta la comparación. Si faltan datos de contexto, prepararlos según `EVALUACION_TEMPORAL.md`.

El servicio `tools` continúa disponible para las tareas anteriores; su suite puede omitir la prueba que requiere scikit-learn. La verificación completa del producto en esta etapa se hace con `ml`.

## Artefactos en DVC local

- `data/evaluation/ml-dev-v1/folds/<fecha>/model.pkl` y `model.json`: estimadores y metadatos por corte.
- `training_index.csv`: trazabilidad de los ejemplos supervisados; no se agrega a Git.
- `forecast.csv`, `scored.csv` y `metrics.json`: mismo esquema de casos/puntuación que el baseline.
- `data/evaluation/ml-dev-v1/metrics.json`: métricas del candidato por corte y globales.
- `data/evaluation/comparison-v1/comparison.json`: aplicación del criterio registrado antes del ajuste.

Estas rutas son resultados de desarrollo reconstruibles, separados del futuro registro operativo inmutable. DVC guarda sus versiones localmente; no se ha ejecutado push ni cambiado el remoto.

## Qué significa superar el criterio

Se exige mismo contexto/casos, completitud total, al menos 5 % de mejora global de pinball, mejora en tres cortes o más, MAE sin aumento y cobertura más cercana o igual al 80 %. El informe muestra cada condición por separado y conserva al baseline si el candidato no cumple.

Un pase técnico solo habilita pasar a un período independiente. La promoción operativa permanece deshabilitada mientras falten resultados de holdout y costos de negocio; también se exige una tolerancia de cobertura explícita para producción. No se inventan costos para decidir ni se publica un modelo como vigente en esta etapa.

## Resultados del primer candidato

Se puntuaron los mismos 49,896 casos, sin predicciones faltantes ni reales pendientes. Los 33 campos de entrada y los 368,874 ejemplos supervisados se reconstruyen desde los snapshots de entrenamiento, sin acceder a los reales de evaluación durante el ajuste.

| Métrica global | Baseline | Candidato híbrido ML |
| --- | ---: | ---: |
| Pinball medio | 22.2737 | 21.1336 |
| MAE de q50 | 61.2278 | 61.2278 |
| WAPE de q50 | 12.8694 % | 12.8694 % |
| Cobertura q10–q90 | 57.3212 % | 64.2296 % |
| Ancho medio del intervalo | 118.6359 | 131.5657 |

La reducción relativa de pinball es 5.1189 %. MAE y WAPE coinciden por diseño, porque la mediana no se modificó. El intervalo es más ancho y cubre más reales, aunque todavía no está suficientemente calibrado.

| Corte | Ejemplos de entrenamiento | Pinball baseline | Pinball ML | Cobertura ML |
| --- | ---: | ---: | ---: | ---: |
| 4 de julio | 65,934 | 20.2118 | 21.6100 | 58.8424 % |
| 11 de julio | 96,228 | 19.5597 | 17.9122 | 65.1836 % |
| 18 de julio | 103,356 | 21.5077 | 19.1529 | 65.4401 % |
| 25 de julio | 103,356 | 27.8157 | 25.8591 | 67.4523 % |

El primer corte empeora y se conserva en el resultado. El candidato mejora los otros tres y cumple todos los criterios técnicos registrados. No hay promoción operativa: además del holdout y los costos pendientes, el error absoluto de cobertura es aproximadamente 0.1577, por encima de la tolerancia 0.10 fijada antes de entrenar.

## Verificar los modelos guardados

```bash
docker compose -f compose.tools.yaml run --rm ml python -m scripts.verify_ml
```

El script conserva una copia previa, restaura el resultado ML desde el caché DVC, vuelve a pronosticar los cuatro cortes cargando los modelos guardados y comprueba igualdad exacta de los CSV. Audita las fechas del índice de entrenamiento, compara todas las medianas con el baseline y verifica que contexto, baseline y dependencias originales permanezcan intactos. La evidencia queda en `reports/generated/ml_verified.json`.

Las 43 pruebas pasaron en la imagen ML; también se verificaron las 122 versiones y `pip check` sin conflictos. Los resultados siguen siendo de desarrollo y locales, pendientes de las etapas de calibración/holdout, costos/pedidos, publicación operativa, seguimiento y Airflow.

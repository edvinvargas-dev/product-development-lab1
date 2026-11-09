# Candidato y criterio fijados antes de entrenar

El baseline mantiene una mediana útil como referencia y presenta cobertura insuficiente de sus cuantiles extremos en desarrollo. El candidato inicial será híbrido: conservar q50 exactamente y aprender q10/q90 condicionales con `HistGradientBoostingRegressor` y pérdida de cuantiles. La [documentación de scikit-learn 1.7](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) describe esta pérdida, soporte categórico y tratamiento de valores faltantes.

Se versionan primero `config/ml.json` y `config/model-selection.json`, antes de entrenar o consultar resultados del candidato. No se cambia el protocolo de julio, sus casos, el baseline ni sus métricas. La mediana compartida debe producir exactamente el mismo MAE/WAPE; la mejora buscada está en los límites de incertidumbre y pinball.

## Criterio de desarrollo

- Mismos hashes de contexto y casos, cortes, cierre de reales y completitud total.
- Pinball medio global al menos 5 % menor que el baseline.
- Pinball menor en al menos tres de cuatro cortes.
- MAE de la mediana sin aumento.
- Distancia de la cobertura al 80 % nominal sin aumento.

Es un criterio técnico para avanzar a otra evaluación. Para sustituir operativamente al vigente también se exigirá un período independiente satisfactorio, error absoluto de cobertura no mayor de 0.10 y costo de negocio no peor con configuración explícita. Mientras falten holdout o costos, no habrá promoción operativa automática. Estos umbrales son decisiones técnicas de prototipo, no costos ni garantías de servicio observados.

## Diseño del candidato inicial

Aprender residuos normalizados respecto a la mediana estacional evita que la escala de una familia determine por sí sola todos los cortes del árbol. La pérdida de entrenamiento se ponderará por esa escala para mantener relación con el pinball en unidades de ventas. No se recortan ni eliminan ventas cero o extremas.

Variables: calendario futuro calculable (día de semana, día/mes y fin de mes), tienda/familia y catálogo estático; estadísticas de ventas y promociones ya observadas; transacciones recientes; último petróleo conocido y su antigüedad; eventos conocidos del pasado aplicables a la tienda. Los precios faltantes se conservan como faltantes y solo se arrastra un precio anterior conocido. No se usan promociones, transacciones, petróleo ni feriados futuros del CSV.

Cada ejemplo histórico tendrá origen y fecha objetivo. Sus características solo usarán observaciones anteriores al origen y disponibles en la fuente antes de él; la etiqueta debe estar conocida en el snapshot del ajuste. Para ejemplos anteriores a la carga histórica inicial se reconstruye disponibilidad histórica del origen simulado, no se inventa una ingesta operativa anterior. En la emisión evaluada se exige además la ingesta real/lógica del snapshot antes del corte, como ya valida el contexto. Si una corrección seleccionada llegó después de un origen histórico, su valor no podrá ser característica de ese ejemplo.

Para evitar una validación aleatoria adicional se desactiva early stopping y se conserva la validación temporal externa. Se fijan semilla, número de iteraciones, tamaño de árbol, frecuencia de orígenes históricos y un hilo. Las reglas completas están en `config/ml.json`.

Los límites pronosticados se proyectan al dominio de ventas no negativas y al orden q10 ≤ q50 ≤ q90, manteniendo fija la mediana. Esto modifica predicciones, no las observaciones usadas al aprender. No constituye una calibración posterior usando los reales del bloque de evaluación.

Las dependencias científicas se instalarán en una imagen adicional, sobre las herramientas existentes, sin actualizar las 117 versiones actuales ni la `.venv` de Windows. Los modelos y resultados irán a DVC local, separados de los del baseline.

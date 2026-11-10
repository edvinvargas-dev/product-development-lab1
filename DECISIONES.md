# Decisiones del laboratorio



## 1. Frecuencia y horizonte del pronóstico



**Propuesta inicial:** ejecutar el sistema diariamente y pronosticar las ventas diarias de los siguientes 7 días para cada tienda y familia de producto.



**Motivo:** empezar con una semana hace que la recomendación sea fácil de interpretar y comparar con las ventas reales. Revisaremos esta propuesta cuando construyamos el flujo.



**Estado:** propuesta por revisar.



## 2. Regla inicial para el pedido sugerido



**Propuesta inicial:** calcular el pedido sugerido a partir del pronóstico de ventas y los costos de faltantes y merma. La fórmula queda pendiente de definir, porque los datos indicados en el laboratorio no incluyen el inventario disponible.



**Estado:** pendiente de definición.

## 3. Diagnóstico verificado el 2026-11-08

- Rama inicial `master`, commits `395b8e9` y `bab9eff`; no hay remoto Git configurado. No se publicará nada sin autorización y destino visible.
- Los cambios anteriores a esta intervención en archivos versionados eran finales de línea. No se descartan.
- Los cinco CSV originales coinciden por MD5 con el manifiesto local de `dataOriginal.dvc`; también coincide el hash del manifiesto. Esto verifica integridad local, no la disponibilidad actual del remoto.
- Remoto DVC configurado de tipo Google Drive. No se leyó el contenido de las credenciales locales ni se ejecutó push/pull.
- Se consultaron solo metadatos de paquetes de Windows: DVC 3.67.1, dvc-gdrive 3.0.1, pyOpenSSL 24.2.1, cryptography 43.0.3 y asyncssh 2.22.0. Se conservan; no se utiliza esa `.venv` desde Linux.
- WSL2 Ubuntu: Docker Desktop responde con motor Linux 29.9.2 y Compose v5.6.1. El sandbox requiere permiso para acceder al socket; se comprobó el servidor con autorización. Airflow todavía no está configurado ni probado.
- Python de WSL no tiene pandas, pytest ni DVC. El intento de crear `.venv-wsl` no se completó porque falta `ensurepip`; esa carpeta parcial está ignorada y no es un entorno listo. No se instalaron paquetes del sistema.
- PDF accesible en Downloads. Se leyó su contenido mediante extracción aproximada de sus cuatro páginas; no se copió ni modificó el documento.

## 4. Exploración y corrección de agregación

El notebook existente se llama `analisis_exploratorio.ipynb`: seis celdas, de las cuales cuatro contienen exploración. Ya muestra dimensiones, fechas, faltantes, ceros y extremos. Se conserva intacto en la raíz.

La agregación final por familia sumaba todas las columnas, incluida `venta_maxima`. El máximo global debe calcularse con `max` sobre los máximos parciales; sumar máximos produce un valor ficticio. Se creó `notebooks/analisis_exploratorio_revisado.ipynb` como copia corregida, retirando la salida de la celda afectada. Las demás salidas son heredadas de la exploración original, no una ejecución nueva. La copia admite ejecución desde raíz o desde `notebooks/`. Su ejecución completa queda pendiente de un entorno con pandas.

`src/audit.py` verifica los cinco archivos sin dependencias externas: train se lee por bloques, las claves repetidas se detectan incluso entre bloques, y se contrasta la cobertura con el calendario completo y el producto de tiendas y familias observadas. Este producto es una referencia de diagnóstico, no una regla que convierta automáticamente ausencias en errores. La exploración no elimina ceros, extremos ni días ausentes.

## 5. Disponibilidad temporal: contrato previo al modelado

Los CSV no incluyen timestamps de publicación, ingesta ni historial de correcciones. Sus fechas no prueban cuándo estaban disponibles. La simulación deberá declarar sus propias reglas, identificadas como supuestos experimentales, antes de construir variables.

Cada entrega tendrá `source`, `data_date`, `available_at`, `delivery_id`, `revision`, hash del contenido y versión del escenario. La ingesta añadirá `ingested_at` a su registro interno. Los timestamps tendrán zona horaria explícita. La fecha del dato, su disponibilidad y su ingesta cumplen funciones distintas y no se intercambian.

Se propone una carga histórica con corte explícito y entregas posteriores por fuente/fecha/revisión. Un generador separado prepara el escenario una sola vez; el producto únicamente lee esa bandeja. Ninguna tarea de ingesta mueve, reescribe ni borra entregas. Una corrección será una nueva entrega; nunca reemplazará el archivo anterior.

Para reproducir una emisión se fijarán el corte, la versión de código, los datos/manifiesto DVC y el estado de conocimiento de esa ejecución. Solo se admitirán entregas disponibles e ingeridas antes del corte. En una simulación retrospectiva, la ingesta lógica simulada se distinguirá de la hora real del replay; no se usará la hora actual como disponibilidad histórica.

Una corrección posterior podrá generar una nueva revisión de resultados o actualizar el seguimiento; no sobrescribirá el pronóstico publicado. Un backfill debe reproducir qué se sabía en su corte, en lugar de usar automáticamente los datos corregidos más recientes.

Pendiente: parametrizar horarios simulados por fuente, corte histórico, demoras y correcciones. Alternativas: escenario conservador sin covariables futuras o calendario/promociones anticipadas con evidencia explícita. Por ahora no se presume que feriados, petróleo, transacciones o promociones futuras estaban disponibles. No se aplica interpolación con valores posteriores al corte.

## 6. Pedido, costos y evaluación pendientes

No hay inventario disponible. La recomendación deberá distinguir una cantidad objetivo de abastecimiento de un pedido neto; no se restará stock ficticio. Los costos reales siguen pendientes: se permitirán escenarios de sensibilidad identificados como simulados, nunca presentados como costos observados. Su configuración será versionada y separada de la lógica.

El PDF describe pedidos semanales y permite definir el horizonte. La ejecución diaria y siete días se mantienen como propuesta por revisar, explicando que una actualización diaria de la recomendación puede coexistir con una operación semanal.

Baseline y ML compartirán los mismos cortes temporales, datos disponibles y métricas. El PDF exige un ML que mejore al baseline: implementar un modelo no basta. El umbral de sustitución y las métricas de costo se definirán antes de comparar resultados.

## 7. Resultados de la auditoría ejecutada

Comando: `python3 -m src.audit`. Informe regenerable en `reports/generated/audit.json`, excluido de Git. Las cifras siguientes son un resumen documental; no sustituyen el informe completo ni versionan los datos en Git.

- Train: 3,000,888 filas, 54 tiendas y 33 familias; del 2013-01-01 al 2017-08-15.
- 1,684 días observados de 1,688 del calendario. Faltan completamente 2013-12-25, 2014-12-25, 2015-12-25 y 2016-12-25. La coincidencia con Navidad sugiere una explicación de negocio, pero los archivos por sí solos no demuestran cierre. No se imputan ceros automáticamente.
- Todas las fechas presentes tienen las 1,782 combinaciones tienda/familia; cero claves duplicadas. La detección cubre también límites de bloques.
- Ningún valor vacío en train. 939,130 ventas cero (aproximadamente 31.30 %), ninguna negativa. Promedio 357.7757 y máximo 124,717. No se eliminan observaciones por estos valores; falta estudiar por tienda/familia y contexto.
- Stores: 54 filas. Holidays: 350 filas entre 2012-03-02 y 2017-12-26. Oil: 1,218 filas entre 2013-01-01 y 2017-08-31, con 43 precios vacíos. Transactions: 83,488 filas entre 2013-01-01 y 2017-08-15. Sin duplicados exactos en estas cuatro fuentes.
- El rango posterior de petróleo/feriados no autoriza a usarlos en una emisión anterior. La falta de precio es distinta de una venta cero. La unicidad por claves de negocio de las fuentes auxiliares y su cobertura conjunta quedan para la validación de ingesta; varios feriados pueden compartir fecha legítimamente.
- Cuatro pruebas sintéticas pasaron con unittest: máximo correcto e independencia de tamaño de bloque, duplicados entre bloques y huecos de calendario, preservación de ceros/extremos y rechazo de ventas no finitas. Son compatibles con pytest; aún no se ejecutó pytest en WSL.

## 8. Primer recorrido temporal implementado

Se eligió para la demostración un escenario conservador, explícitamente simulado y versionado en `config/simulation.json`. Fechas y horas en UTC: ventas y feriados D+1, petróleo y transacciones D+2 a las 12:00. Tiendas es un snapshot estático al inicio; su vigencia histórica no está demostrada por el CSV. No se asume anticipación de promociones ni de feriados futuros. La alternativa de calendario anticipado queda para un escenario posterior con contrato explícito.

Se usan julio de 2017 como carga histórica pequeña y 1–7 de agosto como período de entregas. No es una elección del período final de entrenamiento/validación. Una demora adicional de dos días para transacciones del 2 de agosto permite verificar llegadas tardías sin modificar los valores originales.

Separación de responsabilidades: `src.simulate` produce un escenario nuevo; `src.ingest` solo lee la bandeja y valida antes de actualizar un registro interno; `src.snapshot` selecciona las revisiones conocidas en un corte y publica una fotografía con hashes. Un archivo por fuente/fecha/revisión, salvo stores estático. Las entregas vacías representan que el CSV no contiene observaciones ese día, sin imputar ventas cero. La bandeja generada es externa desde el punto de vista del consumidor.

El registro conserva `ingested_at` lógico simulado y `recorded_at_wall` real por separado. Se eligió polling explícito en vez de asumir que disponibilidad implica ingesta inmediata. El primer polling incorpora la historia elegible; datos disponibles pero no ingeridos aún no se usan. No se puede hacer retroceder un registro de ingesta: un backfill consulta ese registro o reconstruye un escenario independiente con su calendario de polling.

Una corrección reemplaza completamente la entrega fuente/fecha con una revisión nueva y disponibilidad creciente. Se conserva la anterior; no se suman ambas. La implementación selecciona la revisión más alta elegible y reproduce cortes viejos sin usar correcciones posteriores. El generador no inventa correcciones sobre ventas reales: el caso se prueba con filas sintéticas.

Reintentar una ingesta no cambia la primera ingesta ni los bytes del registro. Los snapshots se comparan por contenido y hashes; un destino con otro resultado se rechaza, no se sobrescribe. Se valida todo el lote antes de una actualización atómica del registro. Este diseño requiere un escritor por registro; la futura orquestación deberá serializarlo.

Pruebas ejecutadas: 14 en total con unittest, incluidas las cuatro de auditoría. Las nuevas cubren exclusión de futuros, llegada tardía, precio vacío, entrega vacía, disponibilidad frente a ingesta, corrección/replay, fallo sin actualización parcial, no finitos, duplicados, rutas externas, zona horaria e inmutabilidad. La ejecución con pytest y DVC sigue pendiente del entorno Linux reproducible. Instrucciones detalladas en `docs/INGESTA_TEMPORAL.md`.

### Evidencia de ejecución de la etapa 2

Se generaron 153 entregas a partir de los originales. El primer polling, 2017-08-01T13:00:00Z, admitió 123. Su snapshot contiene 55,242 ventas, 54 tiendas, 5 eventos, 20 precios y 1,620 transacciones. Las transacciones del 2017-08-02 no se seleccionan en el corte del 5 de agosto, pero sí en el del 6, como exige la demora configurada.

Se verificaron por contenido: reintento de ingesta sin nuevas entregas ni cambios al registro; replay del 1 de agosto idéntico después de las ingestas del 5 y 6; hashes de todos los archivos de la bandeja sin cambios. Resumen de evidencia local en `reports/generated/temporal_demo.json`. Esto no sustituye el futuro replay de un pronóstico con Git/DVC.

Un archivo anunciado pero no recibido se informa como `awaiting_delivery` y no se imputa; su ingesta se registra cuando realmente se observa en el polling. Un archivo ya ingerido que desaparece sí detiene el flujo por integridad. Una prueba sintética cubre ambos casos. Se mantiene pendiente la validación conjunta de fuentes y el calendario de polling automatizado.

## 9. Entorno Linux y DVC local

Se eligió un contenedor de herramientas independiente de Airflow en vez de instalar paquetes en el Python 3.14 del host o intentar reutilizar la `.venv` de Windows. La imagen oficial de Python 3.12 está fijada por digest; la versión observada es 3.12.16. La construcción instala paquetes solo dentro de la imagen. Docker/Compose existentes no se reconfiguraron.

Dependencias directas en `requirements/tools.in`: DVC 3.67.1, dvc-gdrive 3.0.1, pytest 8.3.5, pyOpenSSL 24.2.1, cryptography 43.0.3, asyncssh 2.22.0 y pip 25.3. Se conservan las versiones de compatibilidad conocidas, sin modificar Windows. Primero se resolvió este entorno aislado y se comprobó `pip check`; después se congelaron 117 paquetes en `requirements/tools.lock` y se realizó una segunda construcción usando ese archivo. No son versiones que deban actualizarse al ejecutar cada vez.

El contexto de construcción usa una lista permitida mínima en `.dockerignore`: únicamente Dockerfile y requisitos. El código se monta durante la ejecución. El servicio `tools` de `compose.tools.yaml` usa UID 1000 y trabaja sin red; los originales y `.git` son de solo lectura. Se oculta `.dvc/config.local` con un montaje vacío, de modo que las operaciones locales no necesitan acceso a OAuth. El remoto y las credenciales originales permanecen en sus ubicaciones, sin modificación ni copia a la imagen.

Se amplió `.dvcignore` para excluir entornos Python, carpetas de credenciales y auxiliares del recorrido de archivos de DVC. No se excluyen las entradas, el registro ni las salidas derivadas que hay que versionar.

`scenario.dvc` referencia las 153 entregas y su manifiesto (154 archivos); `ingestion.dvc` referencia el estado de conocimiento de los pollings ya realizados. Se registraron en el caché local con `dvc commit --force`, que no es un commit Git ni una subida al remoto. Las referencias están en la raíz para que el directorio `data/` continúe completamente excluido de Git. `dataOriginal.dvc` y el destino remoto se conservaron.

`dvc.yaml` define `snapshot_demo`, que lee estas entradas y el código para producir `data/processed/dvc-demo/2017-08-01`. No genera ni altera la bandeja. Las dependencias incluyen los módulos que ejecuta y las versiones del entorno. La fecha fija pertenece a esta demostración, no establece todavía el período final de evaluación. `dvc.lock` registra sus hashes.

La restauración de DVC puede sustituir salidas y `dvc repro` puede eliminarlas antes de recalcularlas. Por eso se usa una salida derivada separada, nunca la bandeja ni una publicación histórica. La evidencia compara los seis archivos con el snapshot anterior, restaura desde caché y fuerza recálculo sin caché de ejecución: ambos resultados fueron idénticos. Se conservó una copia del resultado previo en `data/verification/`; no se retiraron originales, registro ni entregas.

`scripts/verify_local_dvc.py` deja evidencia regenerable en `reports/generated/dvc_local_replay.json`: hashes, comandos, versiones, entradas intactas y `dvc status --json` igual a `{}`. Esta evidencia es de datos preparados locales, todavía no de un pronóstico ni de recuperación desde Google Drive. Instrucciones en `docs/ENTORNO_DVC.md`.

No se ejecutó push/pull, no se cambió el remoto y no se publicaron artefactos nuevos. La conexión remota desde Linux requerirá una etapa autorizada por separado. También siguen pendientes el punto de control en una rama/commit Git, modelos, CI, Airflow y el tag de entrega.

## 10. Validación conjunta y baseline inicial

Se creó la rama local `feature/baseline-cuantiles`. La identidad de autor no estaba configurada en este entorno; se solicitó nombre y correo al usuario, sin inventarlos ni modificar configuración global. El usuario confirmó después su identidad de autor; se configura únicamente en este repositorio para registrar el punto de control local. No existe publicación remota.

Para poder versionar la exploración sin datos de resultados, se retiraron todas las salidas y contadores de ejecución de la copia revisada en `notebooks/`. El notebook original de la raíz permanece intacto y se agregó a `.gitignore`, para evitar incorporarlo accidentalmente con sus resultados. Sus fórmulas de exploración siguen disponibles en la copia limpia.

`src.validate_snapshot` comprueba las cinco fuentes, hashes, recuentos, fecha de corte, disponibilidad/ingesta, revisiones seleccionadas, claves y referencias al catálogo estático. Las ausencias temporales se reportan; valores inválidos o tiendas desconocidas en este contrato de catálogo completo detienen el flujo. La incorporación futura de tiendas y vigencia histórica del catálogo requerirá ampliar el contrato; no se ha inferido esa historia del CSV actual.

En el corte del 1 de agosto se detectaron 54 tienda/fecha de ventas sin transacciones, 11 fechas sin fila de petróleo y dos precios vacíos. Las referencias de tienda son válidas y las fechas de ventas observadas tienen cobertura completa. Esas ausencias no se transforman en ventas o precios cero ni se interpolan con valores futuros.

El baseline (`src.baseline`) usa cuantiles empíricos por tienda/familia/día de semana sobre los últimos 28 días anteriores al día del corte. Se eligió esta regla transparente como piso de comparación, sin depender de paquetes nuevos. Se requieren tres observaciones del mismo día de semana; alternativamente, siete observaciones de cualquier día de la misma serie en esa ventana. Si no hay historia suficiente, se emite estado explícito y cantidad vacía. Las ventas cero y extremos se incluyen sin recorte.

`config/baseline.json` versiona ventana, horizonte, cuantiles y umbrales técnicos. Los cuantiles 0.1/0.5/0.9 no representan costos ni nivel óptimo de abastecimiento. Con cuatro observaciones del mismo día de semana en esta muestra, la incertidumbre es una referencia empírica sin calibración demostrada. Su cobertura se medirá en la evaluación temporal antes de sacar conclusiones.

El horizonte técnico inicial es de siete días posteriores al día del corte. Para 2017-08-01T13:00:00Z, los objetivos son 2017-08-02 a 2017-08-08; se excluye el propio día parcialmente transcurrido. La propuesta diaria/siete días continúa siendo provisional a nivel de producto. El ajuste usa 49,896 observaciones del 4 al 31 de julio, para 1,782 series. El resultado contiene 37,422 filas en formato largo: tres cuantiles por fecha/tienda/familia.

El baseline numérico usa ventas y calendario. Las otras fuentes participan en validación/contexto; su incorporación como covariables del ML sigue pendiente, y deberá respetar los mismos cortes de disponibilidad. No se hizo aún validación temporal comparativa ni se declararon mejoras de calidad.

DVC incorpora `baseline_fit` y `baseline_predict`, con modelo bajo `models/baseline-demo/` y pronóstico bajo `forecasts/baseline-demo/`. Ambos están excluidos de Git. Se guardan identificadores y hashes de modelo/snapshot/pronóstico sin depender de la hora real de ejecución. Estos directorios son derivados de demostración que DVC puede reconstruir; falta el registro operativo inmutable de publicaciones antes del seguimiento. La función de escritura directa rechaza resultados distintos en el mismo destino.

Pruebas ejecutadas: 23 con unittest y pytest en el contenedor. Se añadieron casos de cuantiles conocidos, prioridad por día de semana, ventana respecto al corte, historial insuficiente, preservación de ceros, exclusión de ventas futuras, tienda desconocida, hash alterado y publicación idempotente. Instrucciones en `docs/BASELINE.md`.

### Evidencia de la etapa 4

`dvc repro baseline_predict` generó las etapas de ajuste y predicción. Después se ejecutó `dvc repro --force --no-run-cache baseline_predict`: los hashes SHA-256 del modelo, del pronóstico y de su manifiesto fueron idénticos. Se comprobaron 12,474 combinaciones fecha/tienda/familia, 37,422 filas con cuantiles crecientes y no negativos, fechas posteriores al corte y cero filas con historia insuficiente en esta muestra. Todas usaron el método del mismo día de semana.

Resumen regenerable de esa ejecución en `reports/generated/baseline_verified.json`; los artefactos completos están en DVC local. No hay evaluación de calidad ni evidencia de publicación remota. El usuario confirmó la identidad de autor y autorizó su configuración local. El punto de control de código, configuración y referencias se registra en la rama `feature/baseline-cuantiles`, sin publicar datos ni repositorio.

## 11. Protocolo temporal de desarrollo

Antes de consultar las métricas se congeló `config/evaluation.json`: cortes 2017-07-04, 2017-07-11, 2017-07-18 y 2017-07-25 a las 13:00 UTC, horizonte de siete días posteriores al corte y cuantiles 0.1/0.5/0.9. Se eligieron cuatro semanas sin solapamiento de objetivos para comparar con el mismo peso temporal y evitar mezclar filas aleatoriamente. Las ventanas del baseline conservan 28 días y avanzan con el corte. No se ajustaron sus parámetros después de ver resultados.

Es una evaluación de desarrollo. Los objetivos terminan el 1 de agosto; esta etapa no puntúa fechas posteriores ni representa todavía un test final de generalización. Los modelos candidatos se podrán desarrollar aquí y luego deberán evaluarse en otro período definido antes de consultarlo. El período desconocido del equipo docente sigue fuera de nuestro control.

Se preparó una bandeja independiente, `evaluacion-julio-v1`, con originales del 1 de junio al 1 de agosto, 249 entregas más manifiesto. Se conservaron los retrasos conservadores de cada fuente y se agregó una demora sintética de dos días para transacciones del 10 de julio. No se cambian ventas ni la bandeja anterior. La nueva referencia `evaluation-scenario.dvc` guarda esta entrada en el caché local.

El calendario tiene carga histórica en el primer polling del 4 de julio y luego polling diario hasta el 3 de agosto, siempre a las 13:00 UTC. Los reales para puntuar se toman con conocimiento hasta ese cierre fijo. Si una entrega real se retrasa más allá del cierre, el caso queda pendiente; una corrección elegible puede revisar la métrica sin reescribir el pronóstico anterior.

`evaluation_context` genera snapshots de cada corte, validación, casos y reales al cierre. Su `logical_ledger.json` conserva disponibilidad e ingesta simuladas; se excluye `recorded_at_wall` del artefacto reproducible porque cambiaría con la hora real de ejecución. Se usa un replay específico de la bandeja congelada para asignar cada entrega a su primer polling elegible, equivalente a la ingesta operativa sobre ese mismo escenario. El registro operativo original y su auditoría real permanecen intactos.

La lista de casos se define con tiendas y familias conocidas en cada corte, antes de mirar los reales del horizonte. El futuro ML debe conservar los mismos hashes de contexto y casos, horizonte, cuantiles y cierre de reales. Se cuenta explícitamente cualquier pronóstico faltante y real pendiente. No se permite atribuir una mejora a un conjunto menor de casos.

`src.metrics` calcula MAE, RMSE, sesgo de mediana (predicción menos real), WAPE, pinball por cuantil/medio y cobertura/ancho del intervalo. WAPE se deja nulo si la suma real es cero, sin constantes de relleno. Las métricas son nulas si no hay casos puntuados. La agregación global usa todos los casos puntuados, no promedios de promedios. Las magnitudes agregan familias de distintas escalas; no representan costos de negocio.

`baseline_backtest` reutiliza el contexto congelado; su función de ajuste recibe solo cada snapshot histórico, mientras el módulo de puntuación recibe los reales después. Los parámetros del baseline son los mismos del punto de control anterior. El costo de negocio queda explícitamente pendiente de configuración; aún no se declara un ganador ni se promueve un modelo.

Se añadieron pruebas de métricas con cálculo manual, denominador cero, casos sin real o pronóstico, orden de claves, cuantiles cruzados/incompletos, protocolo inválido, contexto alterado y replay determinista. Una corrección sintética del real del horizonte cambia su error sin cambiar el identificador del modelo anterior. Guía en `docs/EVALUACION_TEMPORAL.md`.

### Optimización verificada del replay de desarrollo

La primera ejecución real mostraba un costo alto de releer y validar entregas ya conocidas en cada polling. `src.replay` valida una vez cada entrega elegible y calcula el primer polling con disponibilidad menor o igual; mantiene las reglas de archivos pendientes y no lee valores futuros. Se exige una bandeja estática versionada, a diferencia de la ingesta de un origen operativo que puede cambiar físicamente.

Se comprobaron igualdad exacta con la ingesta operativa en pruebas y un prefijo real de 12 pollings/175 entregas antes de detener únicamente ese cálculo de referencia. Se conservó su directorio temporal bajo `reports/generated/reference-replay-interrupted/`. La evidencia de equivalencia está en `reports/generated/replay_equivalence.json`; no contiene nuevos supuestos sobre disponibilidad observada ni altera las entradas.

### Resultados del baseline en el protocolo congelado

Los cuatro cortes puntuaron 49,896 casos de los 49,896 esperados, sin reales pendientes ni predicciones faltantes. Resultado global por casos: MAE 61.2278, RMSE 235.3317, WAPE 12.8694 %, sesgo de mediana -5.9051, pinball medio 22.2737, cobertura q10–q90 57.3212 % y ancho medio 118.6359. El detalle por corte y las definiciones están en `docs/EVALUACION_TEMPORAL.md`; los resultados completos están en `data/evaluation/baseline-dev-v1/` bajo DVC.

La cobertura queda por debajo del 80 % nominal en todos los cortes. Se documenta como una limitación del baseline con cuatro observaciones recientes por día de semana, sin afirmar una causa única ni recalibrarlo después de ver este bloque. El último corte muestra más error, pero no se descarta. Las métricas agregadas mezclan unidades/escalas de familias y no se interpretan como costo de negocio.

Se mantienen la configuración y el protocolo como referencia del futuro ML. Pasaron 37 pruebas con pytest en Linux. `scripts/verify_evaluation.py` comprueba la restauración desde caché y el recálculo sobre el contexto congelado, preservando una copia previa de resultados y generando evidencia local en `reports/generated/evaluation_verified.json`. No se modifican entradas ni se suben artefactos.

### Recuperación de metadatos DVC interrumpidos

La primera verificación restauró y recalculó resultados idénticos, pero `dvc status` encontró propietarios del antiguo proceso cancelado en `.dvc/tmp/rwlock`. Tras confirmar que no había contenedores activos del proyecto y que todos los propietarios eran exactamente el comando de evaluación interrumpido (PID 7), se renombró ese archivo a `rwlock.interrupted-evaluation.bak` para preservarlo y se repitió la verificación. No se borró caché ni se alteraron datos o credenciales. No se implementa retirada automática de bloqueos sin comprobar sus propietarios.

### Verificación final de esta etapa

La verificación repetida terminó correctamente: restauración desde el caché idéntica, recálculo idéntico de todos los archivos de resultados, contexto sin cambios y `dvc status --json` igual a `{}`. Se verificaron además por SHA-256 las 163 entradas/configuraciones protegidas y el notebook original de la demostración anterior: intactos. Evidencia en `reports/generated/evaluation_verified.json`. La evaluación queda guardada en un commit local de la rama existente, sin publicación externa, cambios de remoto ni tag de entrega.

## 12. Primer ML y criterio previo de comparación

El commit local `2f765f6` fijó `config/model-selection.json`, `config/ml.json` y `docs/PLAN_ML.md` antes de entrenar el candidato. Se eligió conservar la mediana del baseline y aprender q10/q90 condicionales con boosting de histogramas: la principal debilidad observada del baseline era su cobertura, y esta arquitectura permite estudiar la incertidumbre sin empeorar por diseño el pronóstico central.

Criterio técnico: mismo contexto/casos/cortes y cierre de reales, completitud total, reducción relativa de pinball medio de al menos 5 %, mejora de pinball en tres cortes o más, MAE sin aumento y distancia de cobertura al 80 % sin aumento. Para sustituir operativamente al vigente también se exige resultado satisfactorio en otro período, error absoluto de cobertura no mayor de 0.10 y costo de negocio no peor con configuración explícita. No se inventan esas evidencias ni se promueve automáticamente un candidato por ganar en desarrollo.

El servicio `ml` reutiliza las herramientas mediante `additional_contexts` de Compose y agrega cinco dependencias científicas en un contexto de construcción mínimo: NumPy 2.3.3, SciPy 1.16.2, scikit-learn 1.7.2, joblib 1.5.2 y threadpoolctl 3.6.0. Se verificaron las 122 versiones y `pip check`; las 117 originales y `requirements/tools.lock` permanecen intactos. No se reutilizó la `.venv` de Windows ni se instalaron paquetes en el host. El runtime conserva ausencia de red, originales de solo lectura y credenciales locales ocultas.

`src.features` construye 33 variables de ventas/promociones anteriores, catálogo estático, transacciones conocidas, último petróleo conocido/antigüedad y eventos anteriores aplicables, además del calendario calculable del objetivo. No se usan valores futuros de los CSV. El indicador del día 15/fin de mes es una hipótesis de calendario, no un dato observado de pagos. Los precios se arrastran solo desde el pasado conocido; si no existen quedan faltantes. Ausencia de transacciones se distingue de cero real.

Cada ejemplo tiene origen y objetivo posterior. Sus variables excluyen datos posteriores al origen y correcciones no disponibles entonces; la etiqueta debe estar conocida en el snapshot de ajuste. Para ejemplos anteriores a la carga histórica inicial se reconstruye disponibilidad del origen simulado sin inventar ingestas operativas previas. La emisión evaluada sí exige también la ingesta antes del corte del snapshot. Los eventos transferidos se excluyen como efectivos en su fecha original. Se conserva el supuesto de catálogo estático, sin inferir su vigencia histórica real.

`src.ml` aprende residuos normalizados respecto a la mediana estacional, ponderados por escala para conservar la relación con pinball en unidades de ventas. Se fijaron semilla, un hilo, cien iteraciones, tamaño de árbol y frecuencia de orígenes históricos; early stopping está desactivado para evitar una partición aleatoria interna. No se eliminan ceros ni extremos. Los límites pronosticados se proyectan a no negativos y al orden de cuantiles, manteniendo q50; no es una calibración posterior usando los reales de evaluación.

Se guardan modelo binario, metadatos/versiones/hashes, fingerprint de entrenamiento e índice temporal de ejemplos. El binario se carga únicamente desde artefactos propios confiables y con hash/versiones comprobados. El contexto común y `src.evaluation` permanecieron sin cambios; un adaptador nuevo reutiliza sus casos y puntuador para ML.

Resultado de un único candidato evaluado: 49,896 casos completos; pinball medio 21.1336 frente a 22.2737 del baseline, mejora relativa 5.1189 %. Mejora en tres cortes; el primero empeora y no se descarta. MAE 61.2278 y WAPE 12.8694 % coinciden exactamente por mantener q50. La cobertura sube de 57.3212 % a 64.2296 %, con ancho medio de 131.5657 frente a 118.6359. El error de cobertura 0.1577 excede la tolerancia operativa 0.10.

`model_comparison` aplica el criterio previo y devuelve pase técnico/candidato para otra evaluación, pero `production_promotion=false`: faltan cobertura suficiente, holdout y costo de negocio. No se cambiaron umbrales ni parámetros después de observar el candidato. La guía `docs/MODELO_ML.md` conserva resultados por corte y límites de interpretación.

Las 43 pruebas pasan en la imagen ML. `scripts/verify_ml.py` restauró artefactos desde DVC y reprodujo idénticos los cuatro pronósticos cargando modelos guardados; auditó 368,874 ejemplos, comprobó las 49,896 medianas y comparación idénticas, contexto/baseline/dependencias intactos y `dvc status --json` igual a `{}`. Evidencia local en `reports/generated/ml_verified.json` y `ml_environment.json`. No hubo publicación externa ni cambios de remoto.

## 13. Revisión de alcance contra el PDF

Se releyeron las cuatro páginas del PDF original a petición del usuario. Lo construido está alineado con pronósticos con incertidumbre, operación temporal de datos, baseline/ML y reproducibilidad. El producto obligatorio aún no está terminado: faltan costos/pedidos, seguimiento de publicaciones, orquestación Airflow 3, CI/GitHub/remoto y evidencias finales.

Los umbrales del 5 %, tres cortes mejorados, tolerancia de cobertura 0.10, cobertura nominal 80 % y holdout interno son decisiones del proyecto, no números exigidos por el PDF. El PDF sí exige definir y justificar un criterio de sustitución; sí exige validación temporal idéntica y ejecución docente sobre un período no publicado. Expresar incertidumbre no obliga por sí solo a demostrar cobertura exacta del 80 %. Una carga histórica inicial tampoco significa cargar todos los originales en cada ejecución.

Se ajusta la prioridad de trabajo para completar primero las piezas obligatorias pendientes. Una calibración adicional o un segundo período interno pueden mejorar el producto, pero no deben postergar pedidos, seguimiento, Airflow y entrega reproducible. Se preservan el experimento y su política registrada, sin alterar umbrales después de observar resultados ni presentar promoción operativa inexistente.

## 14. Objetivos diarios y costos configurables

Se implementó la parte técnica de pedidos y métrica de negocio sin asignar costos reales inexistentes en los CSV. Se solicitó al usuario si dispone de valores reales o prefiere un escenario ilustrativo 9:1. Mientras se define, `config/costs.json` conserva valores nulos y `cost_basis=not_configured`; genera estado `costs_not_configured`, sin cantidades inventadas. El ejemplo 9:1 está separado en `config/examples/costs-relative-9-1.json`, etiquetado como relativo/ilustrativo y no activo.

La regla de un período selecciona el cuantil Cu/(Cu+Co), con costos no negativos y suma positiva. Un cuantil disponible se usa exactamente; uno interior a la grilla se interpola linealmente, como aproximación explícita. No se extrapola fuera del rango: se informa `quantile_not_supported` sin cantidad. Esto permite cambiar costos por defecto o por familia sin alterar la lógica y distingue una configuración todavía incompleta de datos inválidos.

La salida es un objetivo diario continuo de abastecimiento. No hay inventario ni unidades de empaque en los originales: `inventory_status=not_provided` y pedido neto vacío. No se supone stock cero, no se simula arrastre de inventario ni se redondean familias agregadas a cajas. No se suman cuantiles diarios para afirmar un cuantil del total semanal. La configuración define la interpretación `daily_supply_target` y sus límites.

La métrica del ejercicio es Cu*max(real-Q,0)+Co*max(Q-real,0), con costos configurados. Se denomina proxy de déficit/exceso respecto a ventas; no estima merma física o demanda perdida observadas y los valores relativos no son pérdidas monetarias reales. La cantidad se decide antes y sin leer los reales; estos se unen después por corte/fecha/tienda/familia. Faltantes de reales o decisiones se mantienen pendientes, sin reemplazarlos por cero.

DVC agregó `orders_configured` (configuración activa), `orders_example` y `business_example` (solo ejemplo). En el primero hay 12,474 filas con costos pendientes y cantidades vacías. El ejemplo produce 12,474 objetivos y compara baseline/ML sobre los mismos 49,896 casos completos. Costos proxy medios relativos: baseline 222.4772, ML 199.2299; reducción relativa de 10.4493 % en este escenario. Para 9:1 coincide algebraicamente con diez veces pinball de q90; no es una prueba independiente ni ahorro financiero demostrado. No se cambia la decisión de promoción ni se activan costos reales.

Pasaron 53 pruebas con pytest: cambios de costos sin cambios de código, excepciones por familia, interpolación/rango no soportado, datos inválidos, cantidades fraccionarias/cero, historia ausente, real pendiente, cálculo manual, relación con pinball, idempotencia y separación decisor/reales. Las decisiones conservan hashes de pronóstico/configuración e identificadores de contenido. La guía `docs/PEDIDOS_Y_COSTOS.md` documenta ecuaciones, referencia académica y límites. Quedan por definir los costos activos antes de una entrega operativa, y por integrar publicaciones/seguimiento, Airflow/CI/remoto.

La verificación real restauró `orders_example` desde caché, recalculó las tres salidas sin diferencias de hashes, comprobó la identidad costo/pinball para ambos modelos y terminó con `dvc status --json` igual a `{}`. Evidencia en `reports/generated/orders_verified.json`. Los originales, notebook, configuración y bandeja previa se comprobaron intactos por SHA-256. No se publicó nada ni se activó el ejemplo como costos reales.

## 15. Ausencia confirmada de costos y supuesto académico de trabajo

El usuario indicó que no dispone de costos reales y preguntó si estaban en los datasets. Se verificaron las cabeceras de los cinco originales: no contienen costos de faltante/merma, margen ni inventario. El precio del petróleo no permite deducirlos. No se le solicitarán datos reales inexistentes como condición para completar el laboratorio; el PDF exige definir costos en configuración, sin exigir que provengan de estos CSV.

Se adopta técnicamente como supuesto académico de trabajo la relación faltante 9 / exceso-merma 1, en unidades de costo relativas, con `cost_basis=illustrative_relative`. Esa relación fue propuesta por el asistente; el usuario confirmó ausencia de costos reales, no proporcionó esa proporción como dato observado. Justificación: explorar un escenario que prioriza faltantes; el valor es ilustrativo y configurable, no una estimación de Favorita ni moneda. No se supone inventario cero ni se transforma el objetivo en pedido neto.

`config/costs.json` deja de estar pendiente y genera objetivos q90. Se agregó `business_configured` para evaluar con el mismo archivo que decide cantidades, manteniendo el ejemplo independiente y el resto del experimento sin cambios. La métrica sigue siendo proxy de escenario, sin afirmar ahorros reales ni activar promoción operativa del ML. Próxima prioridad: publicaciones inmutables y seguimiento.

Verificación de esta configuración: las 10 pruebas de recomendaciones pasan; se generaron 12,474 objetivos diarios listos con q90, sin inventar inventario. La evaluación de negocio usa el mismo archivo de costos. Se comprobaron intactos por SHA-256 los 163 archivos protegidos del registro previo. Evidencia local en `reports/generated/active_costs_verified.json`; originales y salidas grandes permanecen fuera de Git.

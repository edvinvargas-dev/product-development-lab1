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

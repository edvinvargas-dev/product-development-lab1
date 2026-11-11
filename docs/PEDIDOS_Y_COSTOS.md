# Etapa 7: pedido objetivo y costos configurables

## Decisión que podemos calcular

Se propone una cantidad objetivo diaria por tienda/familia. Los originales no incluyen inventario disponible, mercancía en tránsito ni empaques; por eso el resultado no es un pedido neto de compra. `target_quantity` contiene el objetivo y `net_order_quantity` queda vacío, con `inventory_status=not_provided`.

Cada día se trata como un período independiente de planificación. No se simula arrastre de inventario entre días. Tampoco se suman cuantiles diarios para afirmar que se obtuvo el cuantil del total semanal: eso requeriría otra distribución y supuestos de dependencia. La salida es un plan de objetivos diarios para el horizonte del pronóstico.

Se conservan cantidades fraccionarias porque las familias pueden mezclar unidades de venta; no hay información para imponer cajas o redondeos enteros.

## Regla de costos

Con costo unitario de faltante `Cu` y exceso/merma `Co`, la regla de un período selecciona:

```text
cuantil requerido = Cu / (Cu + Co)
objetivo diario = pronóstico de ese cuantil
```

Es la regla del fractil crítico del [modelo de un período presentado por MIT](https://ocw.mit.edu/courses/15-772j-d-lab-supply-chains-fall-2014/6952be57b43aa185119c6f114908bcc5_MIT15_772JF14_Newsboy.pdf), páginas 2–3. Es óptima dentro de sus supuestos con una distribución correcta; nuestros cuantiles estimados no garantizan ese óptimo real.

Ejemplos de configuración, no costos observados: 1:1 selecciona q50; 9:1 selecciona q90; 3:1 pide q75. Cambiar la relación modifica la recomendación sin cambiar el código. Multiplicar ambos costos por el mismo factor conserva el cuantil y escala solamente la métrica de costo.

Si el cuantil coincide con uno publicado, se usa exactamente. Entre dos cuantiles disponibles se interpola linealmente y se identifica como aproximación. Fuera de su rango se devuelve `quantile_not_supported` sin cantidad; no se extrapola ni se anuncia una cantidad óptima desconocida. Costos negativos, no finitos o ambos cero son configuración inválida y detienen el cálculo.

## Configuración activa y ejemplo separados

`config/costs.json` es la configuración activa. Tras confirmar que el usuario no dispone de costos reales y que los cinco CSV tampoco los contienen, se adoptó como supuesto académico de trabajo la relación faltante 9 / merma 1, en unidades relativas. No se atribuyen esos valores a los datasets ni a Favorita. Justificación: explorar un escenario que penaliza más el faltante que el exceso; la proporción es ilustrativa, modificable y no una estimación empírica. Antes de adoptar el supuesto la configuración estaba pendiente; el estado `not_configured` sigue soportado sin inventar cantidades.

`config/examples/costs-relative-9-1.json` es un ejemplo identificado como `illustrative_relative`, en unidades de costo relativas. Sirve como referencia separada para probar el mecanismo. La configuración activa usa la misma relación ilustrativa con otro identificador de escenario; ninguna representa costos reales.

Cada archivo incluye escenario, procedencia, unidad, pareja de costos por defecto y posibles `family_overrides`. Una excepción de familia debe declarar ambos costos. Para valores reales, la unidad de costo debe ser común y los costos corresponder a la unidad de venta de cada familia. Los valores reales no están disponibles en los CSV.

## Métrica de negocio del ejercicio

Después de emitir, al conocerse una venta real `y`, se puntúa el objetivo `Q` con:

```text
costo proxy = Cu × max(y - Q, 0) + Co × max(Q - y, 0)
```

Se reportan déficit/exceso respecto a ventas observadas. No son quiebres ni merma física medidos: no hay inventario ni demanda perdida observada. Con costos ilustrativos, el resultado no es una pérdida monetaria real ni demuestra ahorro financiero.

Para 9:1 y q90, ese costo es exactamente diez veces pinball de q90, salvo redondeo numérico. Es la misma información expresada con pesos de negocio; no una segunda prueba independiente de calidad. La comparación usa los mismos casos y reales al cierre del protocolo, sin cambiar los modelos ni pasar ventas futuras al decisor.

Un real pendiente no se reemplaza por cero y no se puntúa todavía. Una decisión sin costos, pronóstico o cuantil soportado también queda explícitamente no disponible. Se informan casos esperados/puntuados y pendientes para impedir comparaciones sobre subconjuntos distintos.

## Ejecutar

Con los pronósticos y evaluaciones anteriores disponibles:

```bash
docker compose -f compose.tools.yaml run --rm ml
docker compose -f compose.tools.yaml run --rm ml dvc repro orders_configured business_configured
```

- `orders_configured` usa `config/costs.json` y guarda el estado de configuración/cantidades en `data/orders/configured-demo/`.
- `orders_example` usa solo el ejemplo 9:1 y guarda sus objetivos en `data/orders/illustrative-9-1/`.
- `business_configured` compara baseline y ML con `config/costs.json` en `data/evaluation/business-configured-dev-v1/`; cambiar el archivo actualiza tanto recomendaciones como evaluación.
- `business_example` permanece como evaluación de referencia del ejemplo inicial.

Los CSV y métricas están en DVC local y excluidos de Git. En Git se guardan configuración, código, pruebas y referencias DVC. La escritura directa compara resultados y rechaza sobrescrituras diferentes; DVC puede reconstruir estos directorios derivados de demostración. Todavía falta el registro operativo inmutable de publicaciones.

Cada decisión conserva corte, fecha objetivo, modelo, identificador y escenario/costos usados. Su identificador cambia si cambian el pronóstico o la configuración. Las cantidades se calculan sin leer los reales; el módulo de evaluación los une después por corte/fecha/tienda/familia.

## Pendientes de esta etapa del producto

El supuesto académico ya permite ejecutar la recomendación sin solicitar costos inexistentes. No modifica la política de sustitución ni promueve al ML. Después se integrarán objetivos, pronósticos y configuración en publicaciones inmutables y seguimiento; Airflow/CI/remoto siguen pendientes según la lista del PDF.

## Evidencia ejecutada

Pasaron 53 pruebas. El ejemplo produjo 12,474 objetivos, todos con pedido neto vacío y sin asumir stock. La configuración activa pendiente produjo 12,474 estados `costs_not_configured` con cantidad vacía.

En desarrollo se puntuaron 49,896 casos por modelo con costos ilustrativos 9:1: costo proxy medio 222.4772 para baseline y 199.2299 para ML, reducción relativa 10.4493 %. No son costos reales ni ahorros demostrados. El ejemplo separado se conserva como referencia. La configuración activa adopta ahora esa relación como supuesto académico; este resultado no promueve al ML.

Se restauró `orders_example` desde el caché DVC y se recalcularon las tres salidas: hashes idénticos, identidad costo/pinball comprobada y `dvc status --json` igual a `{}`. Resumen local en `reports/generated/orders_verified.json`.

## Procedencia de los costos: comprobación de los CSV

Se verificaron las cabeceras de los cinco originales. `train` contiene identificador, fecha, tienda, familia, ventas y promociones; `stores` el catálogo; `holidays_events` calendario; `oil` precio del petróleo; `transactions` transacciones por tienda/fecha. No hay costos unitarios de faltantes/merma, márgenes ni inventario. El petróleo no sustituye esos costos.

La consigna pide definir los costos en configuración versionada, no obtenerlos necesariamente de los CSV. El escenario 9:1 es una decisión académica explícita del proyecto ante esa carencia, no una afirmación de que el usuario conoce o proporcionó esa proporción. No requiere datos adicionales para ejecutar el ejercicio y puede revisarse cambiando configuración.

# Etapa 2: de archivos originales a información conocida

## Las tres fechas

`data_date` indica cuándo ocurrió el dato. `available_at` indica cuándo el origen entrega el archivo. `ingested_at` indica cuándo el producto lo incorpora. Para usar una entrega deben cumplirse ambas condiciones: disponibilidad e ingesta menores o iguales al corte del pronóstico. Una venta del día 1 que llega el día 3 no entra en el corte del día 2.

La simulación usa UTC, con zona explícita. No representa horarios reales de Favorita. `recorded_at_wall` conserva por separado la hora real de ejecución del replay; no decide qué datos históricos podía conocer el producto.

## Escenario conservador versionado

Consultar `config/simulation.json`:

| Fuente | Disponibilidad simulada | Tratamiento |
| --- | --- | --- |
| train | D + 1 a las 12:00 UTC | Ventas/promociones observadas del día D |
| stores | Inicio del escenario a las 12:00 UTC | Snapshot estático completo |
| holidays_events | D + 1 a las 12:00 UTC | Eventos observados, sin calendario futuro anticipado |
| oil | D + 2 a las 12:00 UTC | Conservar precios vacíos y fechas sin filas |
| transactions | D + 2 a las 12:00 UTC | Observaciones por tienda/día |

Adicionalmente, la entrega de transacciones del 2017-08-02 tiene dos días extra de demora: estará disponible el 6 de agosto a las 12:00 UTC. No se cambian valores de los CSV.

El horizonte y la frecuencia del futuro pronóstico siguen siendo propuestas. Estos horarios solo regulan la simulación de entradas.

## Productor e ingesta separados

`src.simulate` es el productor externo simulado. Lee los cinco originales en una pasada por fuente, guarda hashes SHA-256 y prepara un directorio nuevo con 153 entregas. El período histórico de demostración es 2017-07-01 a 2017-07-31; las entregas diarias continúan hasta 2017-08-07. No es todavía la carga histórica completa para entrenar un modelo.

Cada archivo cubre fuente/fecha/revisión: por ejemplo `train/2017-08-01/r1.csv`. Hay un manifiesto con identificador de entrega, tipo, fecha, revisión, disponibilidad, filas y hash. Stores se entrega como snapshot único; el resto tiene una entrega por fecha. Los días sin filas en los originales generan archivos con cabecera: esto afirma ausencia de observaciones en el CSV, no ventas cero ni cierre confirmado. Un archivo vacío entregado se distingue de un archivo aún no disponible.

El productor no sobrescribe escenarios existentes. Para probar otra configuración hay que elegir un nuevo directorio; no se altera la bandeja en uso. Solo el productor escribe en ella. La ingesta y los snapshots comprueban los hashes y nunca mueven, borran ni actualizan esas entradas.

## Comandos desde cero

Ejecutar desde la raíz, con Python 3.10 o posterior. No se necesita pandas ni Docker en esta etapa:

```bash
python3 -m unittest discover -s tests -v
python3 -m src.simulate
python3 -m src.ingest --at 2017-08-01T13:00:00Z
python3 -m src.snapshot --cutoff 2017-08-01T13:00:00Z --output data/processed/demo/2017-08-01
```

El primer comando de ingesta incorpora 123 entregas elegibles. El snapshot contiene 55,242 filas de ventas de julio, 54 tiendas, 5 eventos, 20 filas de petróleo y 1,620 filas de transacciones. Las fechas de petróleo sin filas se enumeran en su manifiesto. El precio de un día no se completa con valores posteriores.

Estos comandos ya se ejecutaron en el workspace. No repetir la generación sobre la misma bandeja: el productor la protege y rechazará el destino existente. Para reconstruir una ejecución independiente, usar otro `--output` al generar y pasar ese directorio con `--inbox`, junto con un `--ledger` y destinos de snapshot nuevos. No hace falta borrar nada.

## Avanzar el reloj simulado

```bash
python3 -m src.ingest --at 2017-08-05T13:00:00Z
python3 -m src.snapshot --cutoff 2017-08-05T13:00:00Z --output data/processed/demo/2017-08-05
python3 -m src.ingest --at 2017-08-06T13:00:00Z
python3 -m src.snapshot --cutoff 2017-08-06T13:00:00Z --output data/processed/demo/2017-08-06
```

La entrega `transactions/2017-08-02/r1` no se selecciona el día 5 y sí el día 6. La ingesta es un polling: si no se ejecutó un día, no se inventa una ingesta en ese día. El siguiente polling incorpora lo que esté disponible en ese momento.

El registro interno predeterminado es `data/ingestion/conservador-demo-v1.json`. Un reintento con el mismo corte no cambia sus bytes ni la primera hora de ingesta. El registro avanza en el tiempo: para consultar un corte anterior se usa snapshot, sin retroceder la ingesta.

## Replay de un corte anterior

Después de nuevas ingestas, repetir:

```bash
python3 -m src.snapshot --cutoff 2017-08-01T13:00:00Z --output data/processed/demo/2017-08-01
```

Debe reconstruir el mismo resultado. Si el destino contiene un resultado diferente, se detiene y pide usar otra revisión; no sobrescribe. Cada snapshot guarda los identificadores seleccionados, timestamps lógicos y hashes de sus cinco CSV.

Este replay todavía es local; no constituye la evidencia final de un pronóstico pasado reproducido con Git y DVC.

## Correcciones y validación

Una corrección es un archivo nuevo `r2.csv` y una nueva entrada de manifiesto con disponibilidad posterior. Su contenido reemplaza completamente la entrega de esa fuente/fecha: no es un delta. Un corte selecciona la revisión más alta disponible e ingerida. La revisión anterior se conserva. El generador actual prepara r1 y demoras; las correcciones se demuestran con un productor sintético en las pruebas, sin fabricar ventas corregidas para los originales.

La validación comprueba esquema, hashes, número de filas, fechas, claves duplicadas, campos obligatorios, números finitos y no negativos, e integridad de las revisiones. Permite ceros, extremos, precios vacíos y entregas sin observaciones. Las rutas del manifiesto deben permanecer dentro de la bandeja.

Si una entrega disponible es inválida, el lote falla antes de escribir el registro. Una entrega futura se deja pendiente y sus valores no se leen. Si el catálogo anuncia una entrega cuyo archivo aún no llegó, se informa `awaiting_delivery`, sin imputarla ni hacer fallar el lote; se incorporará en un polling posterior. Si desaparece una entrega ya ingerida, se detiene por pérdida de integridad. Las pruebas verifican también que ingesta/snapshot no modifican la bandeja.

## Límites de esta etapa

- El catálogo de tiendas se supone estático desde el inicio simulado; los originales no prueban su vigencia histórica.
- Las validaciones entre fuentes, calendario de polling automatizado y entrenamiento con historia completa se incorporarán después.
- El registro necesita un único escritor. Airflow deberá serializar las tareas que usen el mismo registro; aún no se garantiza concurrencia entre procesos.
- Escenario, registro y snapshots están ignorados por Git. Falta conectarlos a DVC, sin cambiar el remoto existente.
- No hay modelo, recomendación de pedido ni seguimiento de pronósticos todavía.

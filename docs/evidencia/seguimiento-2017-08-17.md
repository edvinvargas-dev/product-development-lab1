# Evidencia: reporte de seguimiento al último corte (2017-08-17)

**Origen:** `data/tracking/operacion-v1/2017-08-17/report.md`, generado por la tarea `seguimiento` de `reposicion_diaria` en el escenario `operacion-v1`. Está versionado con DVC (`operacion-seguimiento.dvc`), y su SHA-256 empieza por `3947604ec0ad`. Se copia aquí sin cambios para que pueda leerse sin `dvc pull`.

## Cómo leerlo

- **Qué compara:** cada fila es una publicación anterior (un corte) contra las ventas reales conocidas al 2017-08-17. Los datos de Kaggle terminan el 2017-08-15, así que los cortes del 08-15 y 08-16 aún no tienen reales para puntuar.
- **Pendientes:** son días del horizonte de 7 días cuyas ventas todavía no se conocen. No se cuentan como cero.
- **Corrección incorporada:** `train/2017-08-07/r2` reemplazó a la entrega preliminar de la tienda 44, que llegó al 40 %. Los pronósticos publicados no se reescriben; solo el seguimiento usa la revisión.
- **Cobertura observada del intervalo de 80 %:** alrededor de 0.53, lejos del valor nominal. Coincide con la calibración insuficiente del baseline en desarrollo (57 %), y por eso calibrar es una mejora pendiente (DECISIONES 12).
- **Costos:** unidades relativas del supuesto académico 9:1, no pérdidas monetarias.

## Reporte generado

### Seguimiento de desempeño al corte 2017-08-17T13:00:00+00:00

Ventas reales conocidas hasta: **2017-08-15**. Publicaciones evaluadas: **16**.

Correcciones de ventas ya incorporadas: train/2017-08-07/r2.

## Global

- Casos puntuados: 137,214; MAE 75.05; WAPE 0.1672; pinball medio 28.33; cobertura 80 % nominal: 0.5262.
- Costo proxy asimétrico total 29,014,566.11 (unidades relativas), medio 211.45 por decisión; faltante 1,589,503.62 u., exceso 14,709,033.53 u.

## Por publicación

| Corte | Casos | Puntuados | Pendientes | MAE | WAPE | Pinball | Cobertura | Costo medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017-08-01 | 12,474 | 12,474 | 0 | 69.13 | 0.1425 | 25.74 | 0.5332 | 269.45 |
| 2017-08-02 | 12,474 | 12,474 | 0 | 60.76 | 0.1302 | 22.19 | 0.5465 | 201.26 |
| 2017-08-03 | 12,474 | 12,474 | 0 | 60.25 | 0.1308 | 21.80 | 0.5497 | 188.23 |
| 2017-08-04 | 12,474 | 12,474 | 0 | 64.66 | 0.1405 | 23.77 | 0.5378 | 207.81 |
| 2017-08-05 | 12,474 | 12,474 | 0 | 73.53 | 0.1647 | 27.97 | 0.5232 | 210.06 |
| 2017-08-06 | 12,474 | 12,474 | 0 | 82.27 | 0.1906 | 31.80 | 0.5079 | 212.91 |
| 2017-08-07 | 12,474 | 12,474 | 0 | 82.79 | 0.1931 | 31.66 | 0.5057 | 211.26 |
| 2017-08-08 | 12,474 | 12,474 | 0 | 82.08 | 0.1898 | 31.29 | 0.5140 | 211.11 |
| 2017-08-09 | 12,474 | 10,692 | 1,782 | 85.34 | 0.1958 | 32.83 | 0.5079 | 220.71 |
| 2017-08-10 | 12,474 | 8,910 | 3,564 | 91.43 | 0.2032 | 35.52 | 0.5019 | 229.16 |
| 2017-08-11 | 12,474 | 7,128 | 5,346 | 92.69 | 0.2076 | 35.84 | 0.5100 | 196.77 |
| 2017-08-12 | 12,474 | 5,346 | 7,128 | 80.91 | 0.1811 | 30.32 | 0.5357 | 177.83 |
| 2017-08-13 | 12,474 | 3,564 | 8,910 | 56.92 | 0.1332 | 20.17 | 0.5772 | 163.45 |
| 2017-08-14 | 12,474 | 1,782 | 10,692 | 54.09 | 0.1264 | 18.51 | 0.6324 | 179.84 |
| 2017-08-15 | 12,474 | 0 | 12,474 | — | — | — | — | — |
| 2017-08-16 | 12,474 | 0 | 12,474 | — | — | — | — | — |

Los reales pendientes no se tratan como cero. Los costos son un supuesto académico relativo, no pérdidas monetarias observadas.

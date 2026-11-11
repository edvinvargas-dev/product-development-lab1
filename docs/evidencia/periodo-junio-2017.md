# Evidencia: ejecución sobre un período no publicado

**Fecha:** 2026-11-11. **Código:** `main` en `3df246f` (clon limpio desde GitHub).

## Qué se hizo

1. Se clonó el repositorio en una carpeta nueva y se copiaron los cinco CSV de Kaggle a `dataOriginal/`.
2. Solo se modificó `config/operacion.json`:
   - `scenario_id`: `operacion-junio-v1`, con las rutas de `paths` correspondientes;
   - historia: `history_start` 2017-04-01 y `history_end` 2017-05-31; `delivery_end` 2017-06-10;
   - operación: del **2017-06-01 al 2017-06-07**, fechas que la operación `operacion-v1` nunca publicó;
   - `delays: []`, porque la demora original del 2017-08-03 queda fuera del rango (ver README).
3. Se levantó una instalación nueva de Airflow (`docker compose -p lab1-periodo up -d`, puerto 8082, base de datos propia).

No hubo ninguna otra intervención.

## Resultado

| Elemento | Resultado |
|---|---|
| Productor `bandeja_simulada` | `success`: bandeja con 285 entregas |
| Consumidor `reposicion_diaria` | 7 corridas (2017-06-01 a 06-07) en `success`, cada una en menos de 1 minuto |
| Publicaciones | 7 publicaciones inmutables con `provenance.json` (`git_commit` 3df246f) |
| Pronóstico por publicación | 37,422 filas: 1,782 combinaciones de tienda y familia × 7 días × 3 cuantiles |
| Pedido por publicación | 12,474 objetivos diarios (`target_quantity`); `net_order_quantity` vacío |
| Registro de ingesta | 267 entregas registradas |

Las publicaciones de este escenario quedaron en la instalación temporal, que después se eliminó. No forman parte del versionado DVC del escenario `operacion-v1`.

## Primer intento: falla documentada

En el primer intento se conservó `delays` sin cambios. El productor falló con `ValueError: Demora fuera del escenario o para fuente estática`, y el consumidor quedó esperando la bandeja con su sensor, sin publicar nada. Se reinició la instalación desde cero (`down -v`), se vació `delays` y se repitió la prueba. El README documenta ese paso.

## Reporte de seguimiento generado al corte 2017-06-07

### Seguimiento de desempeño al corte 2017-06-07T13:00:00+00:00

Ventas reales conocidas hasta: **2017-06-06**. Publicaciones evaluadas: **6**.

## Global

- Casos puntuados: 26,730; MAE 96.37; WAPE 0.1708; pinball medio 37.45; cobertura 80 % nominal: 0.5220.
- Costo proxy asimétrico total 13,029,159.97 (unidades relativas), medio 487.44 por decisión; faltante 1,344,457.30 u., exceso 929,044.28 u.

## Por publicación

| Corte | Casos | Puntuados | Pendientes | MAE | WAPE | Pinball | Cobertura | Costo medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017-06-01 | 12,474 | 8,910 | 3,564 | 100.86 | 0.1732 | 38.45 | 0.5285 | 489.40 |
| 2017-06-02 | 12,474 | 7,128 | 5,346 | 103.54 | 0.1728 | 40.82 | 0.5142 | 541.74 |
| 2017-06-03 | 12,474 | 5,346 | 7,128 | 104.04 | 0.1797 | 41.12 | 0.5082 | 545.76 |
| 2017-06-04 | 12,474 | 3,564 | 8,910 | 76.04 | 0.1577 | 29.83 | 0.5295 | 394.71 |
| 2017-06-05 | 12,474 | 1,782 | 10,692 | 62.98 | 0.1393 | 23.15 | 0.5466 | 270.87 |
| 2017-06-06 | 12,474 | 0 | 12,474 | — | — | — | — | — |

Los reales pendientes no se tratan como cero. Los costos son un supuesto académico relativo, no pérdidas monetarias observadas.

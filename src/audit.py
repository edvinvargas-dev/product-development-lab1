"""Exploración reproducible, de solo lectura y sin dependencias externas."""

import argparse
import csv
import heapq
import json
import math
from collections import Counter
from datetime import date, timedelta
from itertools import islice
from pathlib import Path


def blocks(reader, size):
    if size < 1:
        raise ValueError("El tamaño del bloque debe ser positivo")
    while block := list(islice(reader, size)):
        yield block


def audit_train(path, chunk_size=50000):
    """Acumula estadísticas; un mapa de bits por fecha detecta claves repetidas.

    Los índices de tienda/familia se asignan globalmente, nunca por bloque.
    Así se detectan también duplicados separados por límites de bloques.
    """
    stores, families, pairs, coverage = set(), set(), {}, {}
    missing, by_family, dates = Counter(), {}, Counter()
    top, total, zeros, negative, duplicates = [], 0, 0, 0, 0
    minimum, maximum = math.inf, -math.inf
    sales_sum = 0.0
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "store_nbr", "family", "sales", "onpromotion", "id"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("train.csv no contiene las columnas requeridas")
        for block in blocks(reader, chunk_size):
            for row in block:
                total += 1
                missing.update(k for k, v in row.items() if v in (None, ""))
                try:
                    day = date.fromisoformat(row["date"]).isoformat()
                    store, family = int(row["store_nbr"]), row["family"]
                    sales = float(row["sales"])
                    if not family or not math.isfinite(sales):
                        raise ValueError("Familia vacía o venta no finita")
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Fila {total + 1}: clave o venta inválida") from exc
                stores.add(store)
                families.add(family)
                pair = (store, family)
                index = pairs.setdefault(pair, len(pairs))
                bit = 1 << index
                seen = coverage.get(day, 0)
                duplicates += bool(seen & bit)
                coverage[day] = seen | bit
                dates[day] += 1
                zeros += sales == 0
                negative += sales < 0
                minimum, maximum = min(minimum, sales), max(maximum, sales)
                sales_sum += sales
                stats = by_family.setdefault(family, {"rows": 0, "zeros": 0, "sales_sum": 0.0, "sales_max": -math.inf})
                stats["rows"] += 1
                stats["zeros"] += sales == 0
                stats["sales_sum"] += sales
                stats["sales_max"] = max(stats["sales_max"], sales)
                heapq.heappush(top, (sales, day, store, family))
                if len(top) > 10:
                    heapq.heappop(top)
    if not total:
        raise ValueError("train.csv está vacío")
    start, end = date.fromisoformat(min(dates)), date.fromisoformat(max(dates))
    calendar = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    expected_daily = len(stores) * len(families)
    incomplete = {day: expected_daily - coverage.get(day, 0).bit_count() for day in calendar
                  if coverage.get(day, 0).bit_count() != expected_daily}
    return {
        "rows": total, "date_min": start.isoformat(), "date_max": end.isoformat(),
        "stores": len(stores), "families": len(families), "observed_days": len(dates),
        "calendar_days": len(calendar), "missing_days": [d for d in calendar if d not in dates],
        "missing_combinations_by_day": incomplete, "duplicate_keys": duplicates,
        "empty_values": dict(missing), "zero_sales": zeros, "negative_sales": negative,
        "sales_min": minimum, "sales_max": maximum, "sales_mean": sales_sum / total,
        "by_family": dict(sorted(by_family.items())),
        "top_sales": [{"sales": s, "date": d, "store_nbr": t, "family": f}
                      for s, d, t, f in sorted(top, reverse=True)],
        "coverage_note": "El producto cartesiano es una referencia diagnóstica; una ausencia no demuestra un dato inválido.",
    }


def audit_auxiliary(path):
    missing, seen, duplicates, days, total = Counter(), set(), 0, [], 0
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            missing.update(k for k, v in row.items() if v in (None, ""))
            key = tuple(row.items())
            duplicates += key in seen
            seen.add(key)
            if "date" in row:
                days.append(date.fromisoformat(row["date"]).isoformat())
        columns = reader.fieldnames
    return {"rows": total, "columns": columns, "empty_values": dict(missing),
            "exact_duplicates": duplicates, "date_min": min(days) if days else None,
            "date_max": max(days) if days else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("dataOriginal"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/audit.json"))
    parser.add_argument("--chunk-size", type=int, default=50000)
    args = parser.parse_args()
    # Una salida nunca puede sobrescribir una entrada, aunque se cambie la extensión.
    if args.output.resolve().is_relative_to(args.data_dir.resolve()):
        parser.error("La salida debe estar fuera del directorio de originales")
    report = {"train.csv": audit_train(args.data_dir / "train.csv", args.chunk_size)}
    for name in ["stores.csv", "holidays_events.csv", "oil.csv", "transactions.csv"]:
        report[name] = audit_auxiliary(args.data_dir / name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Auditoría guardada en {args.output}")
    print(json.dumps({k: v for k, v in report["train.csv"].items() if k not in {"by_family", "top_sales"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

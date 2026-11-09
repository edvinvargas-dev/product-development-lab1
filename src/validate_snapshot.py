"""Validaciones entre fuentes conocidas, sin rellenar ausencias de negocio."""

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from src.deliveries import KEYS, SCHEMAS, json_bytes, sha256, timestamp


def rows(root, source):
    with (Path(root) / f"{source}.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != SCHEMAS[source]:
            raise ValueError(f"Esquema incorrecto: {source}")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Fila incompleta: {source}")
            yield row


def validate(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    cutoff = timestamp(manifest["cutoff"])
    if set(manifest["outputs_sha256"]) != set(SCHEMAS):
        raise ValueError("El snapshot requiere las cinco fuentes")
    selected_keys = set()
    for receipt in manifest["selected"]:
        entry = receipt["entry"]
        available, ingested = timestamp(entry["available_at"]), timestamp(receipt["ingested_at"])
        if not available <= ingested <= cutoff:
            raise ValueError("Entrega no conocida en el corte")
        key = entry["source"], entry["data_date"]
        if key in selected_keys:
            raise ValueError("Varias revisiones de la misma fecha seleccionadas")
        selected_keys.add(key)
    counts, stores, families = {}, set(), set()
    train_store_days, transaction_days, oil_dates, train_dates = set(), set(), set(), set()
    zeros, oil_nulls = 0, 0
    coverage = Counter()
    for source in SCHEMAS:
        if sha256(root / f"{source}.csv") != manifest["outputs_sha256"][source]:
            raise ValueError(f"Hash de snapshot incorrecto: {source}")
    # El catálogo se valida antes de comprobar referencias de ventas/transacciones.
    for row in rows(root, "stores"):
        store = int(row["store_nbr"])
        if store < 1 or store in stores:
            raise ValueError("Clave de tienda inválida o duplicada")
        stores.add(store)
    for source in SCHEMAS:
        count, keys = 0, set()
        for row in rows(root, source):
            count += 1
            if any(v == "" for k, v in row.items() if k != "dcoilwtico"):
                raise ValueError(f"Campo obligatorio vacío: {source}")
            key = tuple(str(int(row[c])) if c == "store_nbr" else row[c] for c in KEYS[source])
            if key in keys:
                raise ValueError(f"Clave duplicada: {source}")
            keys.add(key)
            if "date" in row:
                day = date.fromisoformat(row["date"])
                if day.isoformat() != row["date"] or day >= cutoff.date():
                    raise ValueError("Fecha fuera de la historia conocida")
                if (source, row["date"]) not in selected_keys:
                    raise ValueError("Fila sin entrega seleccionada")
            if "store_nbr" in row and source != "stores":
                store = int(row["store_nbr"])
                if store < 1 or (stores and store not in stores):
                    raise ValueError(f"Tienda desconocida en {source}: {store}")
            for column in ["sales", "dcoilwtico"]:
                if column in row and row[column] != "":
                    value = float(row[column])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError(f"Valor inválido: {column}")
            if source == "train":
                for column in ["id", "onpromotion"]:
                    if int(row[column]) < 0:
                        raise ValueError(f"Valor inválido: {column}")
                families.add(row["family"])
                train_dates.add(row["date"])
                train_store_days.add((row["date"], int(row["store_nbr"])))
                coverage[row["date"]] += 1
                zeros += float(row["sales"]) == 0
            elif source == "transactions":
                if int(row["transactions"]) < 0:
                    raise ValueError("Transacciones negativas")
                transaction_days.add((row["date"], int(row["store_nbr"])))
            elif source == "oil":
                oil_dates.add(row["date"])
                oil_nulls += row["dcoilwtico"] == ""
        counts[source] = count
        if count != manifest["sources"][source]["rows"]:
            raise ValueError(f"Recuento incorrecto: {source}")
    warnings = []
    missing_transactions = len(train_store_days - transaction_days)
    missing_oil = sorted(train_dates - oil_dates)
    if missing_transactions:
        warnings.append("Hay tienda/fecha con ventas sin transacciones conocidas; no se imputan.")
    if missing_oil or oil_nulls:
        warnings.append("Hay fechas sin precio conocido o precio vacío; no se interpolan con futuro.")
    ready = bool(stores and counts["train"])
    if not ready:
        warnings.append("Esperar catálogo/ventas antes de pronosticar.")
    expected = len(stores) * len(families)
    return {"cutoff": cutoff.isoformat(), "status": "ready" if ready else "not_ready",
            "rows": counts, "stores": len(stores), "families": len(families),
            "zero_sales": zeros, "store_dates_without_transactions": missing_transactions,
            "sales_dates_without_oil": missing_oil, "null_oil_prices": oil_nulls,
            "incomplete_observed_sales_dates": {d: n for d, n in coverage.items() if n != expected},
            "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json_bytes(validate(args.snapshot)).decode())


if __name__ == "__main__":
    main()

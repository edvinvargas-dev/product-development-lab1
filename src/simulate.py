"""Productor de escenario: genera una bandeja nueva; nunca sobrescribe otra."""

import argparse
import csv
import json
import tempfile
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from src.deliveries import SCHEMAS, json_bytes, sha256, validate_delivery


VALUE_COLUMN = {"train": "sales", "oil": "dcoilwtico", "transactions": "transactions"}


def last_train_date(originals):
    """Fecha máxima de ventas en los originales: permite operar sobre periodos nuevos."""
    with (Path(originals) / "train.csv").open(newline="", encoding="utf-8-sig") as handle:
        return max(row["date"] for row in csv.DictReader(handle))


def resolve_config(originals, config):
    """`delivery_end: auto` se resuelve a la última venta disponible en los originales."""
    if config.get("delivery_end") == "auto":
        config = {**config, "delivery_end": last_train_date(originals)}
    return config


def checked_incidents(config, start, end):
    incidents = {}
    for item in config.get("corrections", []):
        incidents[item["source"], item["data_date"]] = {
            "type": "correction", "store_nbr": str(item["store_nbr"]),
            "factor": float(item["preliminary_factor"]), "lag_days": item["correction_lag_days"]}
    for item in config.get("invalid_deliveries", []):
        key = item["source"], item["data_date"]
        if key in incidents:
            raise ValueError("Un mismo día no puede tener dos incidentes")
        incidents[key] = {"type": "invalid_values", "lag_days": item["fix_lag_days"]}
    # Un incidente fuera del rango simulado (p. ej. al cambiar de periodo) no aplica.
    incidents = {k: v for k, v in incidents.items() if start <= date.fromisoformat(k[1]) <= end}
    for (source, day), incident in incidents.items():
        if source not in VALUE_COLUMN:
            raise ValueError("Incidente para fuente no soportada")
        if type(incident["lag_days"]) is not int or incident["lag_days"] < 1:
            raise ValueError("La revisión debe llegar al menos un día después")
        if incident["type"] == "correction" and (source != "train" or not 0 <= incident["factor"]):
            raise ValueError("Las correcciones simuladas aplican a ventas con factor no negativo")
    return incidents


def _write_altered(source_path, target, source, columns, incident):
    column = VALUE_COLUMN[source]
    with source_path.open(newline="", encoding="utf-8") as reader, target.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(csv.DictReader(reader)):
            if incident["type"] == "correction" and row["store_nbr"] == incident["store_nbr"]:
                row["sales"] = repr(float(row["sales"]) * incident["factor"])
            elif incident["type"] == "invalid_values" and index == 0:
                row[column] = "-1"  # Valor imposible: debe quedar en cuarentena, no en el modelo.
            writer.writerow(row)


def generate(originals, output, config):
    originals, output = Path(originals).resolve(), Path(output).resolve()
    if output.is_relative_to(originals) or originals.is_relative_to(output):
        raise ValueError("Originales y escenario deben estar separados")
    if output.exists():
        raise FileExistsError("El escenario ya existe: no se sobrescribe; elige otro destino")
    config = resolve_config(originals, config)
    start, historical, end = [date.fromisoformat(config[k]) for k in
                              ["history_start", "history_end", "delivery_end"]]
    if not start <= historical < end:
        raise ValueError("Se requiere history_start <= history_end < delivery_end")
    hour = config["availability_hour_utc"]
    time(hour=hour)  # Validar antes de escribir.
    delays = {}
    for event in config["delays"]:
        key = event["source"], event["data_date"]
        if key in delays or key[0] not in SCHEMAS or type(event["extra_days"]) is not int or event["extra_days"] < 0:
            raise ValueError("Demora inválida o repetida")
        if not start <= date.fromisoformat(key[1]) <= end or key[0] == "stores":
            raise ValueError("Demora fuera del escenario o para fuente estática")
        delays[key] = event["extra_days"]
    incidents = checked_incidents(config, start, end)
    for source in SCHEMAS:
        lag = config["lag_days"][source]
        if type(lag) is not int or lag < (0 if source == "stores" else 1):
            raise ValueError("El escenario conservador exige al menos un día para fuentes fechadas")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preparing-", dir=output.parent) as temp:
        root = Path(temp) / "inbox"
        root.mkdir()
        manifest = {"schema_version": 1, "scenario_id": config["scenario_id"],
                    "simulation": config, "original_sha256": {}, "deliveries": []}
        for source, columns in SCHEMAS.items():
            source_path = originals / f"{source}.csv"
            manifest["original_sha256"][source] = sha256(source_path)
            # Una sola pasada por fuente. Se mantienen buffers de escritura, no datos completos.
            with tempfile.TemporaryDirectory(dir=temp) as spool:
                handles, writers = OrderedDict(), {}
                try:
                    days = [start] if source == "stores" else [start + timedelta(days=i) for i in range((end-start).days+1)]
                    counts = {d.isoformat(): 0 for d in days}
                    for day in days:
                        key = day.isoformat()
                        with (Path(spool) / f"{key}.csv").open("w", newline="", encoding="utf-8") as handle:
                            csv.DictWriter(handle, fieldnames=columns, lineterminator="\n").writeheader()
                    with source_path.open(newline="", encoding="utf-8-sig") as handle:
                        reader = csv.DictReader(handle)
                        if reader.fieldnames != columns:
                            raise ValueError(f"Esquema original incorrecto: {source}")
                        for row in reader:
                            key = start.isoformat() if source == "stores" else row["date"]
                            if key in counts:
                                if key not in handles:
                                    if len(handles) == 32:
                                        old_key, old_handle = handles.popitem(last=False)
                                        old_handle.close()
                                        del writers[old_key]
                                    handles[key] = (Path(spool) / f"{key}.csv").open("a", newline="", encoding="utf-8")
                                    writers[key] = csv.DictWriter(handles[key], fieldnames=columns, lineterminator="\n")
                                handles.move_to_end(key)
                                writers[key].writerow(row)
                                counts[key] += 1
                finally:
                    for handle in handles.values():
                        handle.close()
                for day in days:
                    key = day.isoformat()
                    relative = f"{source}/{key}/r1.csv"
                    path = root / relative
                    path.parent.mkdir(parents=True)
                    (Path(spool) / f"{key}.csv").rename(path)
                    lag = config["lag_days"][source] + delays.get((source, key), 0)
                    available = datetime.combine(day + timedelta(days=lag), time(hour=hour), tzinfo=timezone.utc)
                    entry = {"source": source, "data_date": key, "revision": 1,
                             "delivery_id": f"{source}/{key}/r1", "path": relative,
                             "kind": "snapshot" if source == "stores" else ("historical" if day <= historical else "daily"),
                             "available_at": available.isoformat(), "sha256": sha256(path), "row_count": counts[key]}
                    incident = incidents.get((source, key))
                    if incident is None:
                        validate_delivery(root, entry)
                        manifest["deliveries"].append(entry)
                        continue
                    # La r1 llega alterada (preliminar o inválida); la r2 trae el original después.
                    final = root / f"{source}/{key}/r2.csv"
                    path.rename(final)
                    _write_altered(final, path, source, columns, incident)
                    entry["sha256"] = sha256(path)
                    if incident["type"] == "correction":
                        validate_delivery(root, entry)
                    second = dict(entry, revision=2, delivery_id=f"{source}/{key}/r2", path=f"{source}/{key}/r2.csv",
                                  available_at=(available + timedelta(days=incident["lag_days"])).isoformat(),
                                  sha256=sha256(final))
                    validate_delivery(root, second)
                    manifest["deliveries"].extend([entry, second])
                    manifest.setdefault("incidents", []).append({"source": source, "data_date": key, **incident})
        (root / "manifest.json").write_bytes(json_bytes(manifest))
        root.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, default=Path("dataOriginal"))
    parser.add_argument("--output", type=Path, default=Path("data/scenarios/conservador-demo-v1/inbox"))
    parser.add_argument("--config", type=Path, default=Path("config/simulation.json"))
    args = parser.parse_args()
    result = generate(args.originals, args.output, json.loads(args.config.read_text()))
    print(f"Escenario {result['scenario_id']}: {len(result['deliveries'])} entregas; destino {args.output}")


if __name__ == "__main__":
    main()

"""Productor de escenario: genera una bandeja nueva; nunca sobrescribe otra."""

import argparse
import csv
import json
import tempfile
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from src.deliveries import SCHEMAS, json_bytes, sha256, validate_delivery


def generate(originals, output, config):
    originals, output = Path(originals).resolve(), Path(output).resolve()
    if output.is_relative_to(originals) or originals.is_relative_to(output):
        raise ValueError("Originales y escenario deben estar separados")
    if output.exists():
        raise FileExistsError("El escenario ya existe: no se sobrescribe; elige otro destino")
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
                    validate_delivery(root, entry)
                    manifest["deliveries"].append(entry)
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

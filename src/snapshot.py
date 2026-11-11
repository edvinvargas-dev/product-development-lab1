"""Reconstruye información conocida en un corte; conserva revisiones de resultados."""

import argparse
import csv
import json
import tempfile
from pathlib import Path

from src.deliveries import SCHEMAS, delivery_path, json_bytes, read_manifest, sha256, timestamp, validate_delivery
from src.ingest import context_hash, load_ledger, protect_inputs


def select_receipts(ledger, cutoff):
    cutoff = timestamp(cutoff)
    latest = {}
    for receipt in ledger["receipts"]:
        entry = receipt["entry"]
        if timestamp(receipt["ingested_at"]) < timestamp(entry["available_at"]):
            raise ValueError("Ingesta anterior a disponibilidad")
        if timestamp(entry["available_at"]) > cutoff or timestamp(receipt["ingested_at"]) > cutoff:
            continue
        key = entry["source"], entry["data_date"]
        if key not in latest or entry["revision"] > latest[key]["entry"]["revision"]:
            latest[key] = receipt
    # stores es snapshot completo; no concatenar estados antiguos de la misma tienda.
    stores = [r for r in latest.values() if r["entry"]["source"] == "stores"]
    chosen_store = max(stores, key=lambda r: r["entry"]["data_date"]) if stores else None
    return sorted([r for r in latest.values() if r["entry"]["source"] != "stores" or r is chosen_store],
                  key=lambda r: r["entry"]["delivery_id"])


def snapshot(inbox, ledger_path, cutoff, output):
    protect_inputs(inbox, output)
    output, ledger_path = Path(output).resolve(), Path(ledger_path).resolve()
    if ledger_path.is_relative_to(output) or output.is_relative_to(ledger_path):
        raise ValueError("Snapshot y registro deben tener destinos separados")
    manifest, ledger = read_manifest(inbox), load_ledger(ledger_path)
    if ledger["context_sha256"] != context_hash(manifest):
        raise ValueError("Escenario y registro no coinciden")
    catalog = {e["delivery_id"]: e for e in manifest["deliveries"]}
    selected = select_receipts(ledger, cutoff)
    for receipt in selected:
        entry = receipt["entry"]
        if catalog.get(entry["delivery_id"]) != entry:
            raise ValueError("La entrega cambió desde su ingesta")
        validate_delivery(inbox, entry)
    metadata = {"schema_version": 1, "scenario_id": ledger["scenario_id"],
                "context_sha256": ledger["context_sha256"], "cutoff": timestamp(cutoff).isoformat(),
                "mode": "simulated", "selected": [{"entry": r["entry"], "ingested_at": r["ingested_at"]} for r in selected],
                "sources": {}, "outputs_sha256": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".snapshot-") as temp:
        root = Path(temp) / "result"
        root.mkdir()
        for source, columns in SCHEMAS.items():
            receipts = [r for r in selected if r["entry"]["source"] == source]
            count = 0
            target = root / f"{source}.csv"
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                for receipt in receipts:
                    with delivery_path(inbox, receipt["entry"]).open(newline="", encoding="utf-8-sig") as delivery:
                        for row in csv.DictReader(delivery):
                            writer.writerow(row)
                            count += 1
            metadata["sources"][source] = {"rows": count, "deliveries": len(receipts),
                "status": "observed" if count else ("delivered_empty" if receipts else "not_available"),
                "latest_data_date": max((r["entry"]["data_date"] for r in receipts), default=None),
                "empty_dates": [r["entry"]["data_date"] for r in receipts if r["entry"]["row_count"] == 0]}
            metadata["outputs_sha256"][source] = sha256(target)
        (root / "manifest.json").write_bytes(json_bytes(metadata))
        if output.exists():
            # El mismo corte/estado debe reproducir bytes; jamás reescribir una publicación.
            if (output / "manifest.json").read_bytes() != json_bytes(metadata):
                raise FileExistsError("El destino contiene otro resultado; usa una nueva revisión")
            for source, digest in metadata["outputs_sha256"].items():
                if sha256(output / f"{source}.csv") != digest:
                    raise ValueError("Snapshot previo alterado")
        else:
            root.rename(output)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=Path("data/scenarios/conservador-demo-v1/inbox"))
    parser.add_argument("--ledger", type=Path, default=Path("data/ingestion/conservador-demo-v1.json"))
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = snapshot(args.inbox, args.ledger, args.cutoff, args.output)
    print(json.dumps({"cutoff": result["cutoff"], "sources": result["sources"]}, indent=2))


if __name__ == "__main__":
    main()

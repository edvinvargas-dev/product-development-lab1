"""Ingesta simulada por corte lógico; registro interno persistente e idempotente."""

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.deliveries import delivery_path, json_bytes, read_manifest, timestamp, validate_delivery


def protect_inputs(inbox, output):
    inbox, output = Path(inbox).resolve(), Path(output).resolve()
    originals = (Path(__file__).resolve().parent.parent / "dataOriginal").resolve()
    for protected in [inbox, originals]:
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError("La salida debe estar separada de bandeja y originales")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def context_hash(manifest):
    return hashlib.sha256(json_bytes({k: manifest[k] for k in
                                     ["schema_version", "scenario_id", "simulation", "original_sha256"]})).hexdigest()


def load_ledger(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ingest(inbox, ledger_path, at, quarantine=False):
    """`at` es hora lógica de polling simulada; nunca se deduce de la fecha del dato.

    Validar todo el lote antes de escribir evita registros parciales por datos inválidos.
    Un reintento conserva la primera ingesta. Un backfill consulta el registro existente.
    El llamador debe serializar escrituras a un mismo registro (Airflow: max_active_runs=1).

    Con `quarantine=True` (modo operativo) una entrega nueva cuyo hash coincide con el
    catálogo pero con contenido inválido se rechaza y se registra en `rejections`; nunca
    llega a un snapshot y el resto del lote continúa. Un hash alterado o una entrega ya
    registrada modificada siguen deteniendo todo: son fallas de integridad, no de datos.
    """
    protect_inputs(inbox, ledger_path)
    cutoff = timestamp(at)
    manifest = read_manifest(inbox)
    context = context_hash(manifest)
    ledger = load_ledger(ledger_path) if Path(ledger_path).exists() else {
        "schema_version": 1, "mode": "simulated", "scenario_id": manifest["scenario_id"],
        "context_sha256": context, "receipts": []}
    if ledger["context_sha256"] != context or ledger["mode"] != "simulated":
        raise ValueError("El registro pertenece a otro escenario")
    if any(timestamp(r["ingested_at"]) > cutoff for r in ledger["receipts"]):
        raise ValueError("No se permite retroceder la ingesta; usa snapshot para un backfill")
    catalog = {entry["delivery_id"]: entry for entry in manifest["deliveries"]}
    known = {receipt["entry"]["delivery_id"]: receipt for receipt in ledger["receipts"]}
    for identifier, receipt in known.items():
        if catalog.get(identifier) != receipt["entry"]:
            raise ValueError("Una entrega ya registrada fue modificada o retirada del catálogo")
    rejected = {r["entry"]["delivery_id"] for r in ledger.get("rejections", [])}
    pending, awaiting_delivery, new_rejections = [], [], []
    for entry in manifest["deliveries"]:
        if timestamp(entry["available_at"]) > cutoff or entry["delivery_id"] in rejected:
            continue
        if not delivery_path(inbox, entry).is_file() and entry["delivery_id"] not in known:
            awaiting_delivery.append({"delivery_id": entry["delivery_id"], "status": "awaiting_delivery"})
            continue
        # También verifica que las entregas previas sigan intactas.
        try:
            validate_delivery(inbox, entry)
        except ValueError as error:
            if not quarantine or entry["delivery_id"] in known or str(error).startswith("Hash"):
                raise
            new_rejections.append({"entry": entry, "rejected_at": cutoff.isoformat(), "reason": str(error)})
            continue
        if entry["delivery_id"] not in known:
            pending.append({"entry": entry, "ingested_at": cutoff.isoformat(),
                            "recorded_at_wall": datetime.now(timezone.utc).isoformat()})
    if pending or new_rejections or not Path(ledger_path).exists():
        ledger["receipts"].extend(pending)
        ledger["receipts"].sort(key=lambda r: r["entry"]["delivery_id"])
        if new_rejections:
            ledger["rejections"] = sorted(ledger.get("rejections", []) + new_rejections,
                                          key=lambda r: r["entry"]["delivery_id"])
        atomic_json(ledger_path, ledger)
    result = {"new_deliveries": len(pending), "known_deliveries": len(ledger["receipts"]),
              "logical_ingestion_at": cutoff.isoformat(), "awaiting_delivery": awaiting_delivery}
    if quarantine:  # El modo estricto conserva su contrato previo (replay y artefactos DVC).
        result["rejected"] = [{"delivery_id": r["entry"]["delivery_id"], "reason": r["reason"]} for r in new_rejections]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=Path("data/scenarios/conservador-demo-v1/inbox"))
    parser.add_argument("--ledger", type=Path, default=Path("data/ingestion/conservador-demo-v1.json"))
    parser.add_argument("--at", required=True, help="Hora lógica simulada ISO 8601 con zona")
    args = parser.parse_args()
    print(json.dumps(ingest(args.inbox, args.ledger, args.at), indent=2))


if __name__ == "__main__":
    main()

"""Replay de una bandeja congelada: equivalente a polling, sin releer cada día.

No sustituye la ingesta operativa: requiere archivos estáticos y disponibilidad
simulada explícita. Un escenario diferente debe tener su propia versión DVC.
"""

from bisect import bisect_left

from src.deliveries import delivery_path, read_manifest, timestamp, validate_delivery
from src.ingest import context_hash


def replay_knowledge(inbox, polling):
    if not polling or polling != sorted(set(polling)):
        raise ValueError("El calendario de polling debe ser creciente y único")
    manifest = read_manifest(inbox)
    ledger = {"schema_version": 1, "mode": "simulated", "scenario_id": manifest["scenario_id"],
              "context_sha256": context_hash(manifest), "receipts": []}
    polls = [{"new_deliveries": 0, "known_deliveries": 0, "logical_ingestion_at": at.isoformat(),
              "awaiting_delivery": []} for at in polling]
    for entry in manifest["deliveries"]:
        first = bisect_left(polling, timestamp(entry["available_at"]))
        if first == len(polling):
            continue  # No leer valores posteriores al cierre del experimento.
        if not delivery_path(inbox, entry).is_file():
            for poll in polls[first:]:
                poll["awaiting_delivery"].append({"delivery_id": entry["delivery_id"], "status": "awaiting_delivery"})
            continue
        validate_delivery(inbox, entry)
        ledger["receipts"].append({"entry": entry, "ingested_at": polling[first].isoformat()})
        polls[first]["new_deliveries"] += 1
    known = 0
    for poll in polls:
        known += poll["new_deliveries"]
        poll["known_deliveries"] = known
    ledger["receipts"].sort(key=lambda r: r["entry"]["delivery_id"])
    return ledger, polls

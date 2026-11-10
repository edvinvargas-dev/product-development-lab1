"""Pasos operativos por fecha de corte. Los DAGs de Airflow solo llaman a estas funciones.

Cada paso es idempotente: repetirlo con el mismo corte produce los mismos archivos o
no escribe nada. Las publicaciones son inmutables; un cambio de entradas (código,
configuración o datos conocidos) crea una publicación nueva con otro identificador.
"""

import argparse
import csv
import hashlib
import io
import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.baseline import fit, predict
from src.deliveries import json_bytes, read_manifest, sha256, timestamp
from src.ingest import atomic_json, ingest, load_ledger
from src.orders import ORDER_COLUMNS, csv_bytes, recommendations, validate_costs
from src.simulate import generate, resolve_config
from src.snapshot import snapshot
from src.tracking import report_markdown, track
from src.validate_snapshot import validate

ROOT = Path(__file__).resolve().parent.parent
FORECAST_COLUMNS = ["cutoff", "target_date", "store_nbr", "family", "quantile", "prediction",
                    "model_id", "history_count", "method", "status"]


def load_config(path=None):
    path = Path(path) if path else ROOT / "config/operacion.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["_root"] = str(path.resolve().parent.parent)
    return config


def p(config, key):
    return Path(config["_root"]) / config["paths"][key]


def cutoff_for(config, day):
    """Corte lógico del día `day`: hora fija UTC posterior a la disponibilidad diaria."""
    day = date.fromisoformat(str(day)[:10])
    return datetime(day.year, day.month, day.day, config["operation"]["cutoff_hour_utc"],
                    tzinfo=timezone.utc).isoformat()


def operation_dates(config):
    start = date.fromisoformat(config["operation"]["start_date"])
    end = date.fromisoformat(config["operation"]["end_date"])
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


# ---------------------------------------------------------------- productor (externo)

def prepare_inbox(config):
    """Productor simulado: crea la bandeja una sola vez. No forma parte del consumidor."""
    inbox = p(config, "inbox")
    simulation = resolve_config(p(config, "originals"), config["simulation"])
    if inbox.exists():
        existing = read_manifest(inbox)["simulation"]
        if existing != simulation:
            raise FileExistsError("La bandeja existe con otra configuración; use otro scenario_id")
        return {"status": "exists", "inbox": str(inbox), "delivery_end": simulation["delivery_end"]}
    manifest = generate(p(config, "originals"), inbox, simulation)
    return {"status": "created", "inbox": str(inbox), "deliveries": len(manifest["deliveries"]),
            "delivery_end": simulation["delivery_end"], "incidents": manifest.get("incidents", [])}


# ---------------------------------------------------------------- consumidor

def step_ingest(config, day):
    inbox, ledger = p(config, "inbox"), p(config, "ledger")
    if not (inbox / "manifest.json").is_file():
        raise FileNotFoundError("No hay bandeja: ejecute primero el DAG productor 'bandeja_simulada'")
    cutoff = cutoff_for(config, day)
    if ledger.exists():
        latest = max((timestamp(r["ingested_at"]) for r in load_ledger(ledger)["receipts"]), default=None)
        if latest is not None and latest > timestamp(cutoff):
            # Backfill: lo conocido en ese corte se reconstruye desde el registro, sin reingestar.
            return {"mode": "backfill", "cutoff": cutoff, "new_deliveries": 0, "rejected": []}
    result = ingest(inbox, ledger, cutoff, quarantine=True)
    return {"mode": "forward", "cutoff": cutoff, **result}


def step_snapshot(config, day):
    cutoff = cutoff_for(config, day)
    output = p(config, "snapshots") / day
    metadata = snapshot(p(config, "inbox"), p(config, "ledger"), cutoff, output)
    return {"cutoff": cutoff, "snapshot": str(output),
            "sources": {k: {"rows": v["rows"], "status": v["status"], "latest_data_date": v["latest_data_date"]}
                        for k, v in metadata["sources"].items()}}


def step_validate(config, day):
    """Valida consistencia entre fuentes. Lanza error si hay datos inválidos (detiene el flujo);
    las ausencias esperables (sin precio, sin transacciones, sin ventas aún) solo generan avisos."""
    report = validate(p(config, "snapshots") / day)
    return {k: report[k] for k in ["cutoff", "status", "rows", "stores", "families", "warnings"]}


def code_fingerprint(root):
    digest = hashlib.sha256()
    for path in sorted((Path(root) / "src").glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def git_commit(root):
    """Lee el commit sin depender del binario git (no existe en la imagen de Airflow)."""
    try:
        git = Path(root) / ".git"
        if git.is_file():  # worktree
            git = Path(git.read_text().split(":", 1)[1].strip())
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(" ", 1)[1]
        common = git / "commondir"
        base = (git / common.read_text().strip()).resolve() if common.is_file() else git
        for candidate in [git / ref, base / ref]:
            if candidate.is_file():
                return candidate.read_text().strip()
        for line in (base / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split(" ")[0]
    except (OSError, IndexError):
        pass
    return None


def _write_bundle(target, files):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".pub-") as temp:
        bundle = Path(temp) / "bundle"
        bundle.mkdir()
        for name, content in files.items():
            (bundle / name).write_bytes(content)
        bundle.rename(target)


def step_publish(config, day):
    """Ajusta el modelo vigente, pronostica, deriva el pedido y publica de forma inmutable."""
    root = Path(config["_root"])
    snapshot_dir = p(config, "snapshots") / day
    baseline_config = json.loads((root / config["baseline_config"]).read_text(encoding="utf-8"))
    costs = validate_costs(json.loads((root / config["costs_config"]).read_text(encoding="utf-8")))
    cutoff = cutoff_for(config, day)
    identity = {"cutoff": cutoff, "snapshot_manifest_sha256": sha256(snapshot_dir / "manifest.json"),
                "baseline_config": baseline_config, "cost_config": costs, "code_sha256": code_fingerprint(root)}
    publication_id = hashlib.sha256(json_bytes(identity)).hexdigest()
    target = p(config, "published") / day / publication_id[:12]
    model, report = fit(snapshot_dir, baseline_config)
    files = {"validation.json": json_bytes(report)}
    manifest = {"schema_version": 1, "publication_id": publication_id, **identity,
                "cost_scenario": costs["scenario_id"], "model_type": "empirical_weekday_quantiles_v1",
                "model_role": "vigente", "forecast_start": (timestamp(cutoff).date() + timedelta(days=1)).isoformat()}
    if model is None:
        manifest.update(status="not_ready", model_id=None, reason="Sin catálogo o ventas conocidas; no se inventa pronóstico")
    else:
        forecast_rows = list(predict(model))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=FORECAST_COLUMNS, lineterminator="\n")
        writer.writeheader(); writer.writerows(forecast_rows)
        files["model.json"] = json_bytes(model)
        files["forecast.csv"] = stream.getvalue().encode("utf-8")
        orders = recommendations(({k: str(v) for k, v in r.items()} for r in forecast_rows), costs)
        files["orders.csv"] = csv_bytes(ORDER_COLUMNS, orders)
        states = {s: sum(o["status"] == s for o in orders) for s in sorted({o["status"] for o in orders})}
        manifest.update(status="published", model_id=model["model_id"], horizon_days=baseline_config["horizon_days"],
                        forecast_rows=len(forecast_rows), order_rows=len(orders), order_states=states,
                        files_sha256={n: hashlib.sha256(c).hexdigest() for n, c in sorted(files.items())})
    files["manifest.json"] = json_bytes(manifest)
    if target.exists():
        for name, content in files.items():
            if (target / name).read_bytes() != content:
                raise FileExistsError(f"Publicación {target} alterada: no se sobrescribe")
        return {"status": "already_published", "publication": str(target), "model_status": manifest["status"]}
    # Procedencia: no forma parte del identificador para conservar la idempotencia.
    files["provenance.json"] = json_bytes({"git_commit": git_commit(root),
                                           "published_at_wall": datetime.now(timezone.utc).isoformat()})
    _write_bundle(target, files)
    return {"status": "published", "publication": str(target), "model_status": manifest["status"],
            "order_states": manifest.get("order_states")}


def step_tracking(config, day):
    cutoff = cutoff_for(config, day)
    baseline_config = json.loads((Path(config["_root"]) / config["baseline_config"]).read_text(encoding="utf-8"))
    result = track(p(config, "snapshots") / day, p(config, "published"), cutoff, baseline_config["quantiles"])
    output = p(config, "tracking") / day
    atomic_json(output / "tracking.json", result)
    (output / "report.md").write_text(report_markdown(result), encoding="utf-8")
    atomic_json(p(config, "tracking") / "latest.json", {"cutoff": cutoff, "report": f"{day}/report.md"})
    o = result["overall_technical"]
    return {"cutoff": cutoff, "publications_tracked": result["publications_tracked"],
            "scored_cases": o["scored_cases"], "mean_pinball": o["mean_pinball"],
            "interval_coverage": o["interval_coverage"],
            "mean_proxy_cost": result["overall_business"]["mean_proxy_cost"],
            "corrections_applied": result["corrections_applied"]}


def reproduce(config, day):
    """Recalcula la publicación de `day` en un directorio aparte y la compara byte a byte.

    Usa solo la bandeja y el registro de ingesta versionados (DVC) y el código actual
    (checkout de Git). La procedencia (hora real) se excluye de la comparación."""
    scenario = config["simulation"]["scenario_id"]
    replica = json.loads(json.dumps(config))
    replica["paths"]["snapshots"] = f"data/reproduction/{scenario}/processed"
    replica["paths"]["published"] = f"data/reproduction/{scenario}/published"
    step_snapshot(replica, day)
    result = step_publish(replica, day)
    rebuilt = Path(result["publication"])
    original = p(config, "published") / day / rebuilt.name
    files = sorted(f.name for f in rebuilt.iterdir() if f.name != "provenance.json")
    comparison = {name: (original / name).is_file() and sha256(original / name) == sha256(rebuilt / name)
                  for name in files}
    return {"day": day, "publication_id": rebuilt.name, "original": str(original),
            "original_exists": original.is_dir(), "reproduced": str(rebuilt),
            "identical": original.is_dir() and all(comparison.values()), "files": comparison,
            "sha256": {name: sha256(rebuilt / name) for name in files}}


def run_day(config, day):
    """Secuencia completa de un corte (útil fuera de Airflow y en pruebas)."""
    results = {"ingest": step_ingest(config, day), "snapshot": step_snapshot(config, day),
               "validate": step_validate(config, day)}
    results["publish"] = step_publish(config, day)
    results["tracking"] = step_tracking(config, day)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/operacion.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare-inbox")
    run = commands.add_parser("run")
    run.add_argument("--from-date"); run.add_argument("--to-date")
    again = commands.add_parser("reproduce", help="Reproduce una publicación pasada y la compara")
    again.add_argument("--day", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "prepare-inbox":
        print(json.dumps(prepare_inbox(config), ensure_ascii=False, indent=2))
        return
    if args.command == "reproduce":
        result = reproduce(config, args.day)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["identical"] else 1)
    days = [d for d in operation_dates(config)
            if (not args.from_date or d >= args.from_date) and (not args.to_date or d <= args.to_date)]
    for day in days:
        result = run_day(config, day)
        print(json.dumps({"day": day, "ingest": {k: result["ingest"].get(k) for k in ["mode", "new_deliveries", "rejected"]},
                          "validate": result["validate"]["status"], "publish": result["publish"]["status"],
                          "tracking": {k: result["tracking"][k] for k in ["publications_tracked", "scored_cases", "mean_pinball"]}},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()

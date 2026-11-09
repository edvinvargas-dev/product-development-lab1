"""Contexto temporal congelado y evaluación de desarrollo compartible con ML."""

import argparse
import csv
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from src.baseline import checked_config, fit, predict
from src.deliveries import delivery_path, json_bytes, sha256, timestamp
from src.ingest import protect_inputs
from src.metrics import Accumulator, score
from src.replay import replay_knowledge
from src.snapshot import snapshot
from src.validate_snapshot import rows, validate

CASE_COLUMNS = ["cutoff", "target_date", "store_nbr", "family"]
FORECAST_COLUMNS = [*CASE_COLUMNS, "quantile", "prediction", "model_id", "history_count", "method", "status"]


def write_json(path, value):
    Path(path).write_bytes(json_bytes(value))


def write_csv(path, columns, values):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def tree_hashes(root):
    return {str(p.relative_to(root)): sha256(p) for p in sorted(Path(root).rglob("*")) if p.is_file()}


def build_bundle(output, source, builder):
    output = Path(output).resolve()
    protect_inputs(source, output)
    project = Path(__file__).resolve().parent.parent
    protect_inputs(project / "data/scenarios", output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".evaluation-") as temp:
        root = Path(temp) / "result"
        root.mkdir()
        result = builder(root)
        if output.exists():
            if tree_hashes(output) != tree_hashes(root):
                raise FileExistsError("Resultado distinto: usar una nueva versión de evaluación")
        else:
            root.rename(output)
    return result


def protocol(config):
    if config["purpose"] != "development":
        raise ValueError("Este recorrido solo ejecuta evaluación de desarrollo")
    Accumulator(config["quantiles"])
    start, end = timestamp(config["poll_start"]), timestamp(config["as_of"])
    step, horizon = config["poll_step_days"], config["horizon_days"]
    if type(step) is not int or step < 1 or type(horizon) is not int or horizon < 1 or end < start:
        raise ValueError("Calendario de evaluación inválido")
    polling, current = [], start
    while current <= end:
        polling.append(current)
        current += timedelta(days=step)
    cutoffs = [timestamp(c) for c in config["cutoffs"]]
    if (not cutoffs or cutoffs != sorted(set(cutoffs)) or polling[-1] != end
            or any(c not in polling or c >= end for c in cutoffs)
            or len({c.date() for c in cutoffs}) != len(cutoffs)):
        raise ValueError("Los cortes únicos deben pertenecer al calendario de polling anterior al cierre")
    if any((b.date() - a.date()).days < horizon for a, b in zip(cutoffs, cutoffs[1:])):
        raise ValueError("Este protocolo requiere horizontes de desarrollo sin solapamiento")
    return polling, cutoffs


def prepare(inbox, config, output):
    polling, cutoffs = protocol(config)
    def builder(root):
        # Bandeja congelada: mismo conocimiento que polling, validando cada entrega una vez.
        ledger, polls = replay_knowledge(inbox, polling)
        write_json(root / "logical_ledger.json", ledger)
        write_json(root / "polling.json", polls)
        folds = []
        for cutoff in cutoffs:
            folder = root / "folds" / cutoff.date().isoformat()
            folder.mkdir(parents=True)
            snapshot(inbox, root / "logical_ledger.json", cutoff.isoformat(), folder / "snapshot")
            quality = validate(folder / "snapshot")
            write_json(folder / "validation.json", quality)
            stores = sorted(int(r["store_nbr"]) for r in rows(folder / "snapshot", "stores"))
            families = sorted({r["family"] for r in rows(folder / "snapshot", "train")})
            cases = ({"cutoff": cutoff.isoformat(), "target_date": (cutoff.date() + timedelta(days=i)).isoformat(),
                      "store_nbr": store, "family": family}
                     for i in range(1, config["horizon_days"] + 1) for store in stores for family in families)
            write_csv(folder / "cases.csv", CASE_COLUMNS, cases)
            folds.append({"cutoff": cutoff.isoformat(), "folder": str(folder.relative_to(root)),
                          "cases_sha256": sha256(folder / "cases.csv"),
                          "expected_cases": len(stores) * len(families) * config["horizon_days"],
                          "status": quality["status"]})
            print("Contexto preparado:", cutoff.isoformat(), flush=True)
        snapshot(inbox, root / "logical_ledger.json", config["as_of"], root / "actuals")
        validate(root / "actuals")
        result = {"schema_version": 1, "scenario_id": ledger["scenario_id"], "protocol": config,
                  "inbox_manifest_sha256": sha256(Path(inbox) / "manifest.json"), "folds": folds,
                  "artifacts_sha256": tree_hashes(root)}
        write_json(root / "manifest.json", result)
        return result

    return build_bundle(output, inbox, builder)


def load_context(root):
    root = Path(root)
    context = json.loads((root / "manifest.json").read_text())
    if context["schema_version"] != 1:
        raise ValueError("Contexto de evaluación no soportado")
    _, cutoffs = protocol(context["protocol"])
    if len(context["folds"]) != len(cutoffs):
        raise ValueError("Cantidad de cortes distinta del protocolo")
    for fold, cutoff in zip(context["folds"], cutoffs):
        if (timestamp(fold["cutoff"]) != cutoff
                or fold["folder"] != f"folds/{cutoff.date().isoformat()}"):
            raise ValueError("Ruta/corte de evaluación inconsistente")
        if sha256(root / fold["folder"] / "cases.csv") != fold["cases_sha256"]:
            raise ValueError("Casos de evaluación alterados")
    for relative, expected in context["artifacts_sha256"].items():
        path = delivery_path(root, {"path": relative})
        if sha256(path) != expected:
            raise ValueError(f"Contexto alterado: {relative}")
    return context


def evaluate_baseline(context_path, baseline_config, output):
    context_path = Path(context_path)
    context = load_context(context_path)
    config = context["protocol"]
    checked_config(baseline_config)
    if (baseline_config["horizon_days"] != config["horizon_days"]
            or baseline_config["quantiles"] != config["quantiles"]):
        raise ValueError("Modelo y protocolo deben usar horizonte y cuantiles idénticos")

    def builder(root):
        pooled, folds = Accumulator(config["quantiles"]), []
        for fold in context["folds"]:
            source = context_path / fold["folder"]
            target = root / Path(fold["folder"])
            target.mkdir(parents=True)
            # El ajuste solo recibe el snapshot del corte; no recibe los reales del horizonte.
            model, quality = fit(source / "snapshot", baseline_config)
            forecasts = list(predict(model)) if model is not None else []
            if model is not None:
                write_json(target / "model.json", model)
            write_json(target / "validation.json", quality)
            write_csv(target / "forecast.csv", FORECAST_COLUMNS, forecasts)
            cases = list(read_csv(source / "cases.csv"))
            result, joined = score(cases, forecasts, rows(context_path / "actuals", "train"),
                                   config["quantiles"], accumulators=[pooled])
            write_csv(target / "scored.csv", [*CASE_COLUMNS, "actual", "status", *[f"q{q:g}" for q in config["quantiles"]]], joined)
            result.update(cutoff=fold["cutoff"], cases_sha256=fold["cases_sha256"],
                          model_id=model["model_id"] if model else None,
                          training_date_max=model["training_date_max"] if model else None)
            write_json(target / "metrics.json", result)
            folds.append(result)
            print("Baseline evaluado:", fold["cutoff"], "casos:", result["scored_cases"], flush=True)
        summary = {"schema_version": 1, "model": "empirical_weekday_quantiles_v1",
                   "evaluation_id": config["evaluation_id"], "purpose": config["purpose"],
                   "context_manifest_sha256": sha256(context_path / "manifest.json"),
                   "baseline_config": baseline_config, "as_of": config["as_of"], "folds": folds,
                   "pooled": pooled.summary(),
                   "expected_cases": sum(f["expected_cases"] for f in folds),
                   "actual_pending_cases": sum(f["actual_pending_cases"] for f in folds),
                   "forecast_unavailable_cases": sum(f["forecast_unavailable_cases"] for f in folds),
                   "business_cost": {"status": "pending_cost_configuration", "value": None}}
        write_json(root / "metrics.json", summary)
        write_json(root / "manifest.json", {"schema_version": 1,
                   "context_manifest_sha256": summary["context_manifest_sha256"], "artifacts_sha256": tree_hashes(root)})
        return summary

    return build_bundle(output, context_path, builder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--inbox", type=Path, required=True)
    prep.add_argument("--protocol", type=Path, default=Path("config/evaluation.json"))
    prep.add_argument("--output", type=Path, required=True)
    evaluation = commands.add_parser("baseline")
    evaluation.add_argument("--context", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, default=Path("config/baseline.json"))
    evaluation.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.inbox, json.loads(args.protocol.read_text()), args.output)
        print("Contexto congelado:", len(result["folds"]), "cortes")
    else:
        result = evaluate_baseline(args.context, json.loads(args.config.read_text()), args.output)
        print(json.dumps(result["pooled"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

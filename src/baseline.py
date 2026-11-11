"""Baseline de cuantiles empíricos por tienda, familia y día de semana."""

import argparse
import csv
import hashlib
import io
import json
import math
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from src.deliveries import json_bytes, sha256, timestamp
from src.ingest import protect_inputs
from src.validate_snapshot import rows, validate


def quantile(values, probability):
    """Interpolación lineal: posición (n-1)*q en la muestra ordenada."""
    ordered = sorted(values)
    if not ordered or not 0 < probability < 1 or any(not math.isfinite(v) for v in ordered):
        raise ValueError("Cuantil requiere muestra finita y probabilidad entre 0 y 1")
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def checked_config(config):
    expected = {"horizon_days", "lookback_days", "quantiles", "min_weekday_observations", "min_fallback_observations"}
    if set(config) != expected:
        raise ValueError("Claves de configuración baseline incorrectas")
    for key in expected - {"quantiles"}:
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f"Configuración positiva entera requerida: {key}")
    qs = config["quantiles"]
    if not qs or any(type(q) not in {int, float} or not 0 < q < 1 for q in qs) or qs != sorted(set(qs)):
        raise ValueError("Cuantiles deben ser únicos, crecientes y estar entre 0 y 1")
    return config


def model_identifier(model):
    content = {k: v for k, v in model.items() if k != "model_id"}
    return hashlib.sha256(json_bytes(content)).hexdigest()


def fit(snapshot, config):
    config = checked_config(config)
    report = validate(snapshot)
    if report["status"] != "ready":
        return None, report
    cutoff = timestamp(report["cutoff"])
    first = cutoff.date() - timedelta(days=config["lookback_days"])
    history, families, used_dates = defaultdict(list), set(), set()
    for row in rows(snapshot, "train"):
        families.add(row["family"])
        day = date.fromisoformat(row["date"])
        if first <= day < cutoff.date():
            history[int(row["store_nbr"]), row["family"]].append((day, float(row["sales"])))
            used_dates.add(day)
    stores = sorted(int(row["store_nbr"]) for row in rows(snapshot, "stores"))
    series = []
    for store in stores:
        for family in sorted(families):
            observations = history[store, family]
            all_values = [v for _, v in observations]
            weekdays = {}
            for weekday in range(7):
                values = [v for d, v in observations if d.weekday() == weekday]
                method = "same_weekday"
                if len(values) < config["min_weekday_observations"]:
                    values = all_values
                    method = "all_weekdays_fallback"
                    if len(values) < config["min_fallback_observations"]:
                        values = []
                        method = "insufficient_history"
                weekdays[str(weekday)] = {"method": method, "history_count": len(values),
                    "predictions": [quantile(values, q) for q in config["quantiles"]] if values else None}
            series.append({"store_nbr": store, "family": family, "weekdays": weekdays})
    model = {"schema_version": 1, "model_type": "empirical_weekday_quantiles_v1",
             "cutoff": cutoff.isoformat(), "config": config,
             "snapshot_manifest_sha256": sha256(Path(snapshot) / "manifest.json"),
             "training_date_min": min(used_dates).isoformat() if used_dates else None,
             "training_date_max": max(used_dates).isoformat() if used_dates else None,
             "training_rows": sum(len(v) for v in history.values()), "series": series}
    model["model_id"] = model_identifier(model)
    return model, report


def predict(model):
    if model["schema_version"] != 1 or model["model_type"] != "empirical_weekday_quantiles_v1":
        raise ValueError("Modelo baseline no soportado")
    if model_identifier(model) != model["model_id"]:
        raise ValueError("Identificador de modelo no coincide con su contenido")
    config = checked_config(model["config"])
    cutoff = timestamp(model["cutoff"])
    for offset in range(1, config["horizon_days"] + 1):
        target = cutoff.date() + timedelta(days=offset)
        for series in model["series"]:
            estimate = series["weekdays"][str(target.weekday())]
            for index, q in enumerate(config["quantiles"]):
                yield {"cutoff": model["cutoff"], "target_date": target.isoformat(),
                       "store_nbr": series["store_nbr"], "family": series["family"],
                       "quantile": q, "prediction": estimate["predictions"][index] if estimate["predictions"] is not None else "",
                       "model_id": model["model_id"], "history_count": estimate["history_count"],
                       "method": estimate["method"], "status": "insufficient_history" if estimate["predictions"] is None else "ok"}


def publish(output, files, protected):
    output = Path(output).resolve()
    project = Path(__file__).resolve().parent.parent
    for source in [protected, project / "data/scenarios"]:
        protect_inputs(source, output)
    if output.exists():
        existing = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        if existing != files or any(p.is_dir() for p in output.iterdir()):
            raise FileExistsError("Destino con otro resultado: usa una revisión nueva")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".baseline-") as temp:
        bundle = Path(temp) / "bundle"
        bundle.mkdir()
        for name, content in files.items():
            (bundle / name).write_bytes(content)
        bundle.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("fit")
    train.add_argument("--snapshot", type=Path, required=True)
    train.add_argument("--config", type=Path, default=Path("config/baseline.json"))
    train.add_argument("--output", type=Path, required=True)
    forecast = commands.add_parser("predict")
    forecast.add_argument("--model", type=Path, required=True)
    forecast.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "fit":
        model, report = fit(args.snapshot, json.loads(args.config.read_text()))
        files = {"validation.json": json_bytes(report), "status.json": json_bytes({"status": report["status"]})}
        if model is not None:
            files["model.json"] = json_bytes(model)
        publish(args.output, files, args.snapshot)
        print(json.dumps({"status": report["status"], "series": len(model["series"]) if model else 0,
                          "training_rows": model["training_rows"] if model else 0, "warnings": report["warnings"]}, ensure_ascii=False))
    else:
        # Sin datos conocidos se publica estado explícito, no ventas cero ficticias.
        status = json.loads((args.model / "status.json").read_text())
        files = {"status.json": json_bytes(status)}
        if status["status"] == "ready":
            model = json.loads((args.model / "model.json").read_text())
            stream = io.StringIO(newline="")
            columns = ["cutoff", "target_date", "store_nbr", "family", "quantile", "prediction", "model_id", "history_count", "method", "status"]
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            count = 0
            for row in predict(model):
                writer.writerow(row)
                count += 1
            files["forecast.csv"] = stream.getvalue().encode("utf-8")
            files["manifest.json"] = json_bytes({"schema_version": 1, "model_id": model["model_id"],
                "model_sha256": sha256(args.model / "model.json"), "cutoff": model["cutoff"],
                "forecast_start": (timestamp(model["cutoff"]).date() + timedelta(days=1)).isoformat(),
                "horizon_days": model["config"]["horizon_days"], "rows": count,
                "forecast_sha256": hashlib.sha256(files["forecast.csv"]).hexdigest()})
        publish(args.output, files, args.model)
        print(json.dumps({"status": status["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()

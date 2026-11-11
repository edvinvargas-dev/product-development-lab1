"""Restaurar el ML desde DVC y reproducir pronósticos usando modelos guardados."""

import csv
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path

from src.deliveries import json_bytes, sha256, timestamp
from src.evaluation import FORECAST_COLUMNS, load_context, read_csv, tree_hashes
from src.ml import predict_ml
from src.selection import compare


def main():
    context_path = Path("data/evaluation/dev-context-v1")
    baseline_path = Path("data/evaluation/baseline-dev-v1")
    candidate_path = Path("data/evaluation/ml-dev-v1")
    frozen = json.loads(Path("reports/generated/ml_before.json").read_text()) if Path("reports/generated/ml_before.json").exists() else {
        "context": tree_hashes(context_path), "baseline": tree_hashes(baseline_path),
        "tools_lock": sha256(Path("requirements/tools.lock"))}
    before = tree_hashes(candidate_path)
    context = load_context(context_path)
    parent = Path("data/verification")
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="ml-", dir=parent))/"previous"
    candidate_path.rename(backup)
    try:
        subprocess.run(["dvc", "checkout", "dvc.yaml:ml_backtest"], check=True)
    except Exception:
        if not candidate_path.exists():
            backup.rename(candidate_path)
        raise
    if tree_hashes(candidate_path) != before:
        raise RuntimeError("Restauración ML distinta de la versión original")
    replayed, examples, medians = [], 0, 0
    for fold in context["folds"]:
        source, target = context_path/fold["folder"], candidate_path/fold["folder"]
        metadata = json.loads((target/"model.json").read_text())
        count = 0
        for row in read_csv(target/"training_index.csv"):
            origin = timestamp(row["origin"])
            if not (timestamp(row["latest_feature_available_at"]) <= origin
                    and origin.date().isoformat() < row["target_date"] < metadata["cutoff"][:10]
                    and timestamp(row["label_available_at"]) <= timestamp(metadata["cutoff"])):
                raise RuntimeError("Índice de entrenamiento viola el corte temporal")
            count += 1
        if count != metadata["training_examples"]:
            raise RuntimeError("Cantidad de ejemplos inconsistente")
        examples += count
        baseline_medians = {(r["target_date"], int(r["store_nbr"]), r["family"]): float(r["prediction"])
                            for r in read_csv(baseline_path/fold["folder"]/"forecast.csv") if float(r["quantile"]) == 0.5}
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=FORECAST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in predict_ml(target, source/"snapshot", list(read_csv(source/"cases.csv"))):
            writer.writerow(row)
            if row["quantile"] == 0.5:
                key = row["target_date"], int(row["store_nbr"]), row["family"]
                if row["prediction"] != baseline_medians[key]:
                    raise RuntimeError("La mediana dejó de coincidir con el baseline")
                medians += 1
        digest = hashlib.sha256(stream.getvalue().encode()).hexdigest()
        if digest != sha256(target/"forecast.csv"):
            raise RuntimeError("Pronóstico regenerado distinto del guardado")
        replayed.append({"cutoff": fold["cutoff"], "model_id": metadata["model_id"], "forecast_sha256": digest})
        print("Pronóstico reproducido:", fold["cutoff"], flush=True)
    baseline = json.loads((baseline_path/"metrics.json").read_text())
    candidate = json.loads((candidate_path/"metrics.json").read_text())
    policy = json.loads(Path("config/model-selection.json").read_text())
    comparison = compare(baseline, candidate, policy)
    if comparison != json.loads(Path("data/evaluation/comparison-v1/comparison.json").read_text()):
        raise RuntimeError("Comparación no reproducible")
    if (tree_hashes(context_path) != frozen["context"] or tree_hashes(baseline_path) != frozen["baseline"]
            or sha256(Path("requirements/tools.lock")) != frozen["tools_lock"]):
        raise RuntimeError("Se modificaron el contexto, baseline o dependencias originales")
    status = json.loads(subprocess.check_output(["dvc", "status", "--json"], text=True))
    if status:
        raise RuntimeError("DVC tiene cambios pendientes")
    result = {"restored_identical": True, "forecasts_replayed_identically": replayed, "context_baseline_and_dependencies_unchanged": True,
              "audited_training_examples": examples, "identical_baseline_medians": medians,
              "comparison_reproduced": True, "technical_pass": comparison["technical_pass"],
              "production_promotion": comparison["production_promotion"], "dvc_status": status, "backup": str(backup)}
    Path("reports/generated/ml_verified.json").write_bytes(json_bytes(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

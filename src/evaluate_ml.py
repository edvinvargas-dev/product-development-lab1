"""Adaptador ML sobre el contexto y el puntuador ya congelados del baseline."""

import argparse
import json
from pathlib import Path

from src.deliveries import sha256
from src.evaluation import CASE_COLUMNS, FORECAST_COLUMNS, build_bundle, load_context, read_csv, tree_hashes, write_csv, write_json
from src.metrics import Accumulator, score
from src.ml import fit_ml, predict_ml, validate_config
from src.validate_snapshot import rows


def evaluate(context_path, baseline_config, config, output):
    context_path = Path(context_path)
    context = load_context(context_path)
    protocol = context["protocol"]
    validate_config(config)
    for parameter in ["horizon_days", "quantiles"]:
        if config[parameter] != protocol[parameter] or baseline_config[parameter] != protocol[parameter]:
            raise ValueError("Horizonte/cuantiles deben coincidir con el contexto común")

    def builder(root):
        pooled, folds = Accumulator(protocol["quantiles"]), []
        for fold in context["folds"]:
            source, target = context_path/fold["folder"], root/fold["folder"]
            target.mkdir(parents=True)
            print("Ajustando candidato:", fold["cutoff"], flush=True)
            model, quality = fit_ml(source/"snapshot", baseline_config, config, target)
            cases = list(read_csv(source/"cases.csv"))
            forecasts = list(predict_ml(target, source/"snapshot", cases)) if model else []
            write_json(target/"validation.json", quality)
            write_csv(target/"forecast.csv", FORECAST_COLUMNS, forecasts)
            result, joined = score(cases, forecasts, rows(context_path/"actuals", "train"), protocol["quantiles"], [pooled])
            write_csv(target/"scored.csv", [*CASE_COLUMNS, "actual", "status", *[f"q{q:g}" for q in protocol["quantiles"]]], joined)
            result.update(cutoff=fold["cutoff"], cases_sha256=fold["cases_sha256"], model_id=model["model_id"] if model else None,
                          training_date_max=model["training_date_max"] if model else None,
                          training_examples=model["training_examples"] if model else 0)
            write_json(target/"metrics.json", result)
            folds.append(result)
            print("Candidato evaluado:", fold["cutoff"], "casos:", result["scored_cases"], flush=True)
        summary = {"schema_version": 1, "model": "hgb_residual_tails_v1", "evaluation_id": protocol["evaluation_id"],
                   "purpose": protocol["purpose"], "context_manifest_sha256": sha256(context_path/"manifest.json"),
                   "baseline_config": baseline_config, "ml_config": config, "as_of": protocol["as_of"], "folds": folds,
                   "pooled": pooled.summary(), "expected_cases": sum(f["expected_cases"] for f in folds),
                   "actual_pending_cases": sum(f["actual_pending_cases"] for f in folds),
                   "forecast_unavailable_cases": sum(f["forecast_unavailable_cases"] for f in folds),
                   "business_cost": {"status": "pending_cost_configuration", "value": None}}
        write_json(root/"metrics.json", summary)
        write_json(root/"manifest.json", {"schema_version": 1, "context_manifest_sha256": summary["context_manifest_sha256"],
                                         "artifacts_sha256": tree_hashes(root)})
        return summary

    return build_bundle(output, context_path, builder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--baseline-config", type=Path, default=Path("config/baseline.json"))
    parser.add_argument("--config", type=Path, default=Path("config/ml.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.context, json.loads(args.baseline_config.read_text()), json.loads(args.config.read_text()), args.output)
    print(json.dumps(result["pooled"], indent=2))


if __name__ == "__main__":
    main()

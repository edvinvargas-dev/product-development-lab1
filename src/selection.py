"""Criterio explícito: una mejora de desarrollo no implica promoción operativa."""

import argparse
import json
import math
from pathlib import Path

from src.baseline import publish
from src.deliveries import json_bytes


def compare(baseline, candidate, policy):
    if (policy["primary_metric"] != "mean_pinball" or not policy["require_identical_cases_and_complete_scores"]
            or not policy["coverage_distance_must_not_increase"] or not policy["production_requires_independent_holdout"]
            or not policy["production_requires_business_cost_noninferiority"]):
        raise ValueError("Esta versión requiere las salvaguardas del protocolo de selección")
    for field in ["evaluation_id", "purpose", "context_manifest_sha256", "as_of", "expected_cases", "baseline_config"]:
        if baseline[field] != candidate[field]:
            raise ValueError(f"Comparación inválida: {field} no coincide")
    left = [(f["cutoff"], f["cases_sha256"], f["expected_cases"]) for f in baseline["folds"]]
    right = [(f["cutoff"], f["cases_sha256"], f["expected_cases"]) for f in candidate["folds"]]
    if left != right:
        raise ValueError("Los modelos no usan los mismos cortes/casos")
    old, new = baseline["pooled"], candidate["pooled"]
    complete = all(r["expected_cases"] > 0 and r["pooled"]["scored_cases"] == r["expected_cases"]
                   and r["actual_pending_cases"] == 0 and r["forecast_unavailable_cases"] == 0
                   and all(f["scored_cases"] == f["expected_cases"] for f in r["folds"]) for r in [baseline, candidate])
    available = all(isinstance(m[field], (int, float)) and math.isfinite(m[field]) for m in [old, new]
                    for field in ["mean_pinball", "mae", "interval_coverage", "nominal_interval_coverage"])
    improvement = (old["mean_pinball"]-new["mean_pinball"])/old["mean_pinball"] if available and old["mean_pinball"] > 0 else None
    improved_folds = sum(a["mean_pinball"] is not None and b["mean_pinball"] is not None
                         and b["mean_pinball"] < a["mean_pinball"] for a, b in zip(baseline["folds"], candidate["folds"]))
    old_distance = abs(old["interval_coverage"]-old["nominal_interval_coverage"]) if available else None
    new_distance = abs(new["interval_coverage"]-new["nominal_interval_coverage"]) if available else None
    gates = {"identical_complete_cases": complete, "metrics_available": available,
             "pinball_improvement": improvement is not None and improvement >= policy["minimum_relative_improvement"],
             "mae_noninferior": available and new["mae"] <= old["mae"]*(1+policy["maximum_mae_relative_increase"]),
             "enough_improved_folds": improved_folds >= policy["minimum_improved_folds"],
             "coverage_distance_noninferior": available and new_distance <= old_distance}
    technical = all(gates.values())
    production = {"technical_pass": technical,
                  "coverage_tolerance": available and new_distance <= policy["production_maximum_absolute_coverage_error"],
                  "independent_holdout_passed": False, "business_cost_noninferiority_proven": False}
    return {"policy_id": policy["policy_id"], "context_manifest_sha256": candidate["context_manifest_sha256"],
            "baseline_model": baseline["model"], "candidate_model": candidate["model"],
            "relative_pinball_improvement": improvement, "improved_folds": improved_folds,
            "development_gates": gates, "technical_pass": technical,
            "development_decision": "candidate_for_holdout" if technical else "retain_baseline",
            "production_gates": production, "production_promotion": all(production.values()),
            "production_decision": "retain_baseline_pending_required_evidence",
            "baseline_metrics": old, "candidate_metrics": new}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("config/model-selection.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()), json.loads(args.policy.read_text()))
    # Las dos entradas deben quedar fuera del destino.
    from src.ingest import protect_inputs
    protect_inputs(args.candidate, args.output)
    publish(args.output, {"comparison.json": json_bytes(result)}, args.baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

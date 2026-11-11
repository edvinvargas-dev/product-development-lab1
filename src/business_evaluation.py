"""Comparación de objetivos diarios usando costos explícitos y reales congelados."""

import argparse
import json
from pathlib import Path

from src.deliveries import delivery_path, sha256
from src.evaluation import build_bundle, load_context, read_csv, tree_hashes, write_csv, write_json
from src.orders import ORDER_COLUMNS, recommendations, score_orders, validate_costs
from src.validate_snapshot import rows

SCORE_COLUMNS = [*ORDER_COLUMNS, "actual", "shortage_proxy_units", "excess_proxy_units", "asymmetric_proxy_cost", "evaluation_status"]


def verify_bundle(root):
    manifest = json.loads((Path(root)/"manifest.json").read_text())
    for relative, expected in manifest["artifacts_sha256"].items():
        if sha256(delivery_path(root, {"path": relative})) != expected:
            raise ValueError("Artefacto de evaluación alterado")
    return json.loads((Path(root)/"metrics.json").read_text())


def evaluate(context_path, baseline_path, candidate_path, costs, output):
    context_path, baseline_path, candidate_path = map(Path, [context_path, baseline_path, candidate_path])
    validate_costs(costs)
    context = load_context(context_path)
    context_hash = sha256(context_path/"manifest.json")
    summaries = {"baseline": verify_bundle(baseline_path), "candidate": verify_bundle(candidate_path)}
    for summary in summaries.values():
        if summary["context_manifest_sha256"] != context_hash:
            raise ValueError("Modelos y reales no comparten contexto")
        if [(f["cutoff"], f["cases_sha256"], f["expected_cases"]) for f in summary["folds"]] != [
                (f["cutoff"], f["cases_sha256"], f["expected_cases"]) for f in context["folds"]]:
            raise ValueError("Casos de modelos distintos del protocolo")
    from src.ingest import protect_inputs
    for source in [baseline_path, candidate_path]:
        protect_inputs(source, output)

    def builder(root):
        report = {"schema_version": 1, "context_manifest_sha256": context_hash,
                  "as_of": context["protocol"]["as_of"], "cost_config": costs,
                  "metric_type": "asymmetric_daily_target_proxy", "quantity_type": "daily_supply_target",
                  "inventory_available": False, "observed_financial_loss": False, "models": {}}
        for name, source in [("baseline", baseline_path), ("candidate", candidate_path)]:
            all_orders, all_actuals, folds = [], [], []
            for fold in context["folds"]:
                expected = {(r["target_date"], int(r["store_nbr"]), r["family"]) for r in read_csv(context_path/fold["folder"]/"cases.csv")}
                # El decisor solo recibe pronósticos/costos; no recibe los reales.
                orders = recommendations(read_csv(source/fold["folder"]/"forecast.csv"), costs)
                if {(r["target_date"], r["store_nbr"], r["family"]) for r in orders} != expected:
                    raise ValueError("Las decisiones no cubren los casos congelados")
                actuals = [{"cutoff": fold["cutoff"], "target_date": r["date"], "store_nbr": r["store_nbr"],
                            "family": r["family"], "actual": r["sales"]} for r in rows(context_path/"actuals", "train")
                           if (r["date"], int(r["store_nbr"]), r["family"]) in expected]
                metrics, joined = score_orders(orders, actuals)
                folder = root/name/fold["folder"]
                folder.mkdir(parents=True)
                write_csv(folder/"orders.csv", ORDER_COLUMNS, orders)
                write_csv(folder/"scored_orders.csv", SCORE_COLUMNS, joined)
                write_json(folder/"metrics.json", metrics)
                folds.append({"cutoff": fold["cutoff"], **metrics})
                all_orders.extend(orders); all_actuals.extend(actuals)
            global_metrics, _ = score_orders(all_orders, all_actuals)
            report["models"][name] = {"forecast_model": summaries[name]["model"], "folds": folds, "pooled": global_metrics}
        left, right = [report["models"][name]["pooled"] for name in ["baseline", "candidate"]]
        complete = (left["expected_cases"] > 0 and left["expected_cases"] == right["expected_cases"]
                    and all(m["scored_cases"] == m["expected_cases"] for m in [left, right]))
        improvement = ((left["total_proxy_cost"]-right["total_proxy_cost"])/left["total_proxy_cost"]
                       if complete and left["total_proxy_cost"] > 0 else None)
        report["comparison"] = {"identical_complete_cases": complete, "relative_proxy_cost_improvement": improvement,
                                "candidate_noninferior_in_scenario": complete and right["total_proxy_cost"] <= left["total_proxy_cost"],
                                "real_business_costs_verified": False, "production_promotion": False}
        write_json(root/"metrics.json", report)
        write_json(root/"manifest.json", {"schema_version": 1, "context_manifest_sha256": context_hash,
                                          "artifacts_sha256": tree_hashes(root)})
        return report

    return build_bundle(output, context_path, builder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--costs", type=Path, default=Path("config/costs.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from src.ingest import protect_inputs
    protect_inputs(args.costs, args.output)
    result = evaluate(args.context, args.baseline, args.candidate, json.loads(args.costs.read_text()), args.output)
    print(json.dumps({"cost_basis": result["cost_config"]["cost_basis"], "models": {n:r["pooled"] for n,r in result["models"].items()},
                      "comparison": result["comparison"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

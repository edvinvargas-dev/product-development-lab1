"""Objetivos diarios de abastecimiento y costo asimétrico, sin inventario ficticio."""

import argparse
import csv
import hashlib
import io
import json
import math
from bisect import bisect_left
from datetime import date
from pathlib import Path

from src.baseline import publish
from src.deliveries import json_bytes, sha256, timestamp

ORDER_COLUMNS = ["decision_id", "cutoff", "target_date", "store_nbr", "family", "model_id", "cost_scenario",
                 "cost_basis", "cost_unit", "shortage_per_unit", "excess_per_unit", "required_quantile", "quantile_method",
                 "target_quantity", "quantity_type", "inventory_status", "net_order_quantity", "status"]


def cost_pair(pair):
    if set(pair) != {"shortage_per_unit", "excess_per_unit"}:
        raise ValueError("Se requieren ambos costos unitarios")
    values = list(pair.values())
    if any(type(v) not in {int, float} or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Costos deben ser números finitos no negativos")
    if not math.isfinite(sum(values)) or sum(values) <= 0:
        raise ValueError("Suma de costos debe ser positiva y finita")
    return pair


def validate_costs(config):
    expected = {"schema_version", "scenario_id", "description", "cost_basis", "cost_unit", "defaults", "family_overrides",
                "quantile_rule", "quantity_type"}
    if set(config) != expected or config["schema_version"] != 1:
        raise ValueError("Esquema de costos no soportado")
    if config["quantile_rule"] != "linear_interpolation_no_extrapolation" or config["quantity_type"] != "daily_supply_target":
        raise ValueError("Política de cantidades/cuantiles no soportada")
    if config["cost_basis"] not in {"not_configured", "illustrative_relative", "business_provided"}:
        raise ValueError("Origen de costos no reconocido")
    if not all(isinstance(config[k], str) and config[k] for k in ["scenario_id", "description", "cost_unit"]):
        raise ValueError("Escenario, descripción y unidad requeridos")
    if not isinstance(config["family_overrides"], dict):
        raise ValueError("Costos por familia deben ser un mapa")
    if config["cost_basis"] == "not_configured":
        if config["defaults"] != {"shortage_per_unit": None, "excess_per_unit": None} or config["family_overrides"]:
            raise ValueError("Costos pendientes no pueden incluir cifras activas")
    else:
        cost_pair(config["defaults"])
        for family, pair in config["family_overrides"].items():
            if not isinstance(family, str) or not family:
                raise ValueError("Nombre de familia requerido")
            cost_pair(pair)
    return config


def choose_quantile(predictions, probability):
    levels = sorted(predictions)
    if probability in predictions:
        return predictions[probability], "exact"
    position = bisect_left(levels, probability)
    if not 0 < position < len(levels):
        return None, "quantile_not_supported"
    low, high = levels[position-1], levels[position]
    value = predictions[low] + (predictions[high]-predictions[low])*(probability-low)/(high-low)
    return value, "linear_interpolation"


def recommendations(forecasts, config):
    validate_costs(config)
    config_hash = hashlib.sha256(json_bytes(config)).hexdigest()
    groups = {}
    for row in forecasts:
        cutoff = timestamp(row["cutoff"]).isoformat()
        day = date.fromisoformat(row["target_date"])
        store = int(row["store_nbr"])
        if day <= timestamp(cutoff).date() or store < 1 or not row["family"] or not row["model_id"]:
            raise ValueError("Clave/fecha de pronóstico inválida")
        key = cutoff, day.isoformat(), store, row["family"]
        group = groups.setdefault(key, {"model_id": row["model_id"], "predictions": {}, "states": set()})
        q = float(row["quantile"])
        if not 0 < q < 1 or q in group["predictions"] or group["model_id"] != row["model_id"]:
            raise ValueError("Cuantil duplicado/inválido o modelos mezclados")
        state = row["status"]
        if state == "ok":
            value = float(row["prediction"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Predicción no válida para abastecimiento")
        elif state == "insufficient_history" and row["prediction"] == "":
            value = None
        else:
            raise ValueError("Estado de pronóstico inválido")
        group["predictions"][q] = value
        group["states"].add(state)
    output = []
    for key, group in sorted(groups.items()):
        predictions = group["predictions"]
        if len(group["states"]) != 1:
            raise ValueError("Disponibilidad inconsistente de cuantiles")
        if group["states"] == {"ok"} and [predictions[q] for q in sorted(predictions)] != sorted(predictions.values()):
            raise ValueError("Cuantiles cruzados")
        cost = config["family_overrides"].get(key[3], config["defaults"])
        quantity, required, method = None, None, "not_selected"
        if config["cost_basis"] == "not_configured":
            state = "costs_not_configured"
        elif group["states"] != {"ok"}:
            state = "forecast_unavailable"
        else:
            required = cost["shortage_per_unit"]/(cost["shortage_per_unit"]+cost["excess_per_unit"])
            quantity, method = choose_quantile(predictions, required)
            state = "ready" if quantity is not None else "quantile_not_supported"
        identity = {"key": key, "model_id": group["model_id"], "forecast_quantiles": predictions, "cost_config_sha256": config_hash}
        output.append({"decision_id": hashlib.sha256(json_bytes(identity)).hexdigest(),
            **dict(zip(["cutoff", "target_date", "store_nbr", "family"], key)), "model_id": group["model_id"],
            "cost_scenario": config["scenario_id"], "cost_basis": config["cost_basis"], "cost_unit": config["cost_unit"],
            **cost, "required_quantile": required, "quantile_method": method, "target_quantity": quantity,
            "quantity_type": config["quantity_type"], "inventory_status": "not_provided", "net_order_quantity": None,
            "status": state})
    return output


def asymmetric_cost(actual, quantity, shortage, excess):
    if any(not math.isfinite(v) or v < 0 for v in [actual, quantity]):
        raise ValueError("Ventas/cantidad deben ser finitas y no negativas")
    cost_pair({"shortage_per_unit": shortage, "excess_per_unit": excess})
    short, over = max(actual-quantity, 0), max(quantity-actual, 0)
    return short, over, shortage*short+excess*over


def score_orders(orders, actuals):
    known = {}
    for row in actuals:
        key = timestamp(row["cutoff"]).isoformat(), row["target_date"], int(row["store_nbr"]), row["family"]
        if key in known:
            raise ValueError("Real duplicado")
        value = row["actual"]
        if value not in ("", None):
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError("Venta real inválida")
        else:
            value = None
        known[key] = value
    evaluated, short_total, over_total, cost_total = 0, 0.0, 0.0, 0.0
    pending, unavailable, joined, seen = 0, 0, [], set()
    for order in orders:
        key = order["cutoff"], order["target_date"], order["store_nbr"], order["family"]
        if key in seen:
            raise ValueError("Decisión duplicada")
        seen.add(key)
        actual = known.get(key)
        quantity = order["target_quantity"]
        pending += actual is None
        unavailable += order["status"] != "ready"
        short = over = cost = None
        state = "actual_pending" if actual is None else "decision_unavailable"
        if actual is not None and order["status"] == "ready":
            short, over, cost = asymmetric_cost(actual, quantity, order["shortage_per_unit"], order["excess_per_unit"])
            evaluated += 1; short_total += short; over_total += over; cost_total += cost
            state = "scored"
        joined.append({**order, "actual": actual, "shortage_proxy_units": short, "excess_proxy_units": over,
                       "asymmetric_proxy_cost": cost, "evaluation_status": state})
    return {"expected_cases": len(orders), "scored_cases": evaluated, "actual_pending_cases": pending,
            "decision_unavailable_cases": unavailable, "shortage_proxy_units": short_total if evaluated else None,
            "excess_proxy_units": over_total if evaluated else None,
            "total_proxy_cost": cost_total if evaluated else None,
            "mean_proxy_cost": cost_total/evaluated if evaluated else None}, joined


def csv_bytes(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def build(forecast_path, config, output):
    forecast_path = Path(forecast_path)
    source_manifest = forecast_path.parent/"manifest.json"
    if source_manifest.is_file():
        expected = json.loads(source_manifest.read_text()).get("forecast_sha256")
        if expected is not None and sha256(forecast_path) != expected:
            raise ValueError("Hash del pronóstico no coincide con su manifiesto")
    with forecast_path.open(newline="", encoding="utf-8") as handle:
        orders = recommendations(csv.DictReader(handle), config)
    states = {s: sum(r["status"] == s for r in orders) for s in sorted({r["status"] for r in orders})}
    manifest = {"schema_version": 1, "forecast_sha256": sha256(forecast_path),
                "cost_config": config, "cost_config_sha256": hashlib.sha256(json_bytes(config)).hexdigest(),
                "quantity_type": "daily_supply_target", "net_inventory_order_available": False,
                "rows": len(orders), "states": states}
    publish(output, {"orders.csv": csv_bytes(ORDER_COLUMNS, orders), "manifest.json": json_bytes(manifest)}, forecast_path.parent)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--costs", type=Path, default=Path("config/costs.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.costs.read_text())
    from src.ingest import protect_inputs
    protect_inputs(args.costs, args.output)
    print(json.dumps(build(args.forecast, config, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

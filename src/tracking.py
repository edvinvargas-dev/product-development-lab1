"""Seguimiento: compara publicaciones pasadas con las ventas reales conocidas en un corte.

Las publicaciones nunca se modifican. El seguimiento se recalcula en cada corte con la
última revisión conocida de las ventas, de modo que una corrección posterior se refleja
automáticamente (reprocesamiento) sin reescribir lo que se publicó.
"""

import csv
import json
from datetime import date
from pathlib import Path

from src.deliveries import timestamp
from src.metrics import Accumulator, score
from src.orders import score_orders


def _number(value):
    return None if value in ("", None) else float(value)


def load_actuals(snapshot_dir, since):
    """Ventas observadas desde `since` (inclusive), tal como se conocen en el snapshot."""
    actuals = []
    with (Path(snapshot_dir) / "train.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["date"] >= since:
                actuals.append({"date": row["date"], "store_nbr": row["store_nbr"],
                                "family": row["family"], "sales": row["sales"]})
    return actuals


def corrected_dates(snapshot_dir):
    manifest = json.loads((Path(snapshot_dir) / "manifest.json").read_text(encoding="utf-8"))
    return sorted(s["entry"]["delivery_id"] for s in manifest["selected"]
                  if s["entry"]["source"] == "train" and s["entry"]["revision"] > 1)


def track_publication(publication, actuals, quantiles, overall):
    manifest = json.loads((publication / "manifest.json").read_text(encoding="utf-8"))
    with (publication / "forecast.csv").open(newline="", encoding="utf-8") as handle:
        forecasts = list(csv.DictReader(handle))
    cases, seen = [], set()
    for row in forecasts:
        key = row["target_date"], row["store_nbr"], row["family"]
        if key not in seen:
            seen.add(key)
            cases.append({"cutoff": row["cutoff"], "target_date": row["target_date"],
                          "store_nbr": int(row["store_nbr"]), "family": row["family"]})
    technical, joined = score(cases, forecasts, actuals, quantiles, accumulators=(overall,))
    truth = {(j["target_date"], j["store_nbr"], j["family"]): j["actual"] for j in joined}
    with (publication / "orders.csv").open(newline="", encoding="utf-8") as handle:
        orders = []
        for row in csv.DictReader(handle):
            orders.append({**row, "store_nbr": int(row["store_nbr"]),
                           "target_quantity": _number(row["target_quantity"]),
                           "shortage_per_unit": _number(row["shortage_per_unit"]),
                           "excess_per_unit": _number(row["excess_per_unit"])})
    order_actuals = [{"cutoff": o["cutoff"], "target_date": o["target_date"], "store_nbr": o["store_nbr"],
                      "family": o["family"], "actual": truth.get((o["target_date"], o["store_nbr"], o["family"]), "")}
                     for o in orders]
    business, _ = score_orders(orders, order_actuals)
    return {"publication_id": manifest["publication_id"], "cutoff": manifest["cutoff"],
            "model_id": manifest["model_id"], "cost_scenario": manifest["cost_scenario"],
            "technical": technical, "business": business}


def track(snapshot_dir, publications_root, cutoff, quantiles):
    """Evalúa todas las publicaciones con corte anterior a `cutoff`."""
    cutoff = timestamp(cutoff)
    publications = []
    for path in sorted(Path(publications_root).glob("*/*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["status"] == "published" and timestamp(manifest["cutoff"]) < cutoff:
            publications.append(path.parent)
    since = min((json.loads((p / "manifest.json").read_text())["forecast_start"] for p in publications),
                default=cutoff.date().isoformat())
    actuals = load_actuals(snapshot_dir, since)
    overall = Accumulator(quantiles)
    results = [track_publication(p, actuals, quantiles, overall) for p in publications]
    business_keys = ["scored_cases", "actual_pending_cases", "shortage_proxy_units", "excess_proxy_units", "total_proxy_cost"]
    totals = {k: sum(r["business"][k] or 0 for r in results) for k in business_keys}
    totals["mean_proxy_cost"] = totals["total_proxy_cost"] / totals["scored_cases"] if totals["scored_cases"] else None
    return {"schema_version": 1, "cutoff": cutoff.isoformat(),
            "snapshot_manifest": str(Path(snapshot_dir).name),
            "actuals_known_through": max((a["date"] for a in actuals), default=None),
            "corrections_applied": corrected_dates(snapshot_dir),
            "publications_tracked": len(results), "overall_technical": overall.summary(),
            "overall_business": totals, "publications": results}


def _fmt(value, digits=2):
    return "—" if value is None else f"{value:,.{digits}f}"


def report_markdown(result):
    lines = [f"# Seguimiento de desempeño al corte {result['cutoff']}", "",
             f"Ventas reales conocidas hasta: **{result['actuals_known_through']}**. "
             f"Publicaciones evaluadas: **{result['publications_tracked']}**.", ""]
    if result["corrections_applied"]:
        lines += ["Correcciones de ventas ya incorporadas: " + ", ".join(result["corrections_applied"]) + ".", ""]
    o, b = result["overall_technical"], result["overall_business"]
    lines += ["## Global", "",
              f"- Casos puntuados: {o['scored_cases']:,}; MAE {_fmt(o['mae'])}; WAPE {_fmt(o['wape'], 4)}; "
              f"pinball medio {_fmt(o['mean_pinball'])}; cobertura 80 % nominal: {_fmt(o['interval_coverage'], 4)}.",
              f"- Costo proxy asimétrico total {_fmt(b['total_proxy_cost'])} (unidades relativas), "
              f"medio {_fmt(b['mean_proxy_cost'])} por decisión; faltante {_fmt(b['shortage_proxy_units'])} u., "
              f"exceso {_fmt(b['excess_proxy_units'])} u.", "",
              "## Por publicación", "",
              "| Corte | Casos | Puntuados | Pendientes | MAE | WAPE | Pinball | Cobertura | Costo medio |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for p in result["publications"]:
        t, c = p["technical"], p["business"]
        lines.append(f"| {p['cutoff'][:10]} | {t['expected_cases']:,} | {t['scored_cases']:,} | "
                     f"{t['actual_pending_cases']:,} | {_fmt(t['mae'])} | {_fmt(t['wape'], 4)} | "
                     f"{_fmt(t['mean_pinball'])} | {_fmt(t['interval_coverage'], 4)} | {_fmt(c['mean_proxy_cost'])} |")
    lines += ["", "Los reales pendientes no se tratan como cero. Los costos son un supuesto académico relativo, "
              "no pérdidas monetarias observadas.", ""]
    return "\n".join(lines)

"""Métricas comunes para modelos que comparten casos y cuantiles de evaluación."""

import math


class Accumulator:
    def __init__(self, quantiles):
        if (len(quantiles) < 3 or quantiles != sorted(set(quantiles))
                or 0.5 not in quantiles or not all(0 < q < 1 for q in quantiles)):
            raise ValueError("Se requieren cuantiles ordenados con mediana y extremos interiores a (0,1)")
        self.quantiles = quantiles
        self.n = self.covered = 0
        self.absolute = self.squared = self.signed = self.actual_sum = self.width = 0.0
        self.pinball = {q: 0.0 for q in quantiles}

    def add(self, actual, predictions):
        if set(predictions) != set(self.quantiles):
            raise ValueError("Conjunto de cuantiles distinto del protocolo")
        values = [predictions[q] for q in self.quantiles]
        if (not math.isfinite(actual) or actual < 0 or values != sorted(values)
                or any(not math.isfinite(v) or v < 0 for v in values)):
            raise ValueError("Reales/pronósticos inválidos o cuantiles cruzados")
        error = predictions[0.5] - actual
        self.n += 1
        self.absolute += abs(error)
        self.squared += error * error
        self.signed += error
        self.actual_sum += actual
        self.covered += values[0] <= actual <= values[-1]
        self.width += values[-1] - values[0]
        for q, prediction in predictions.items():
            residual = actual - prediction
            self.pinball[q] += max(q * residual, (q - 1) * residual)

    def summary(self):
        return {"scored_cases": self.n,
                "mae": self.absolute / self.n if self.n else None,
                "rmse": math.sqrt(self.squared / self.n) if self.n else None,
                "bias_prediction_minus_actual": self.signed / self.n if self.n else None,
                "wape": self.absolute / self.actual_sum if self.actual_sum else None,
                "wape_status": "defined" if self.actual_sum else "no_positive_actual_sum",
                "pinball_by_quantile": {str(q): v / self.n if self.n else None for q, v in self.pinball.items()},
                "mean_pinball": sum(self.pinball.values()) / (self.n * len(self.quantiles)) if self.n else None,
                "interval_coverage": self.covered / self.n if self.n else None,
                "nominal_interval_coverage": self.quantiles[-1] - self.quantiles[0],
                "mean_interval_width": self.width / self.n if self.n else None}


def case_key(row):
    return row["target_date"], int(row["store_nbr"]), row["family"]


def score(cases, forecasts, actuals, quantiles, accumulators=()):
    """Unir por claves, no por posición. Un real pendiente nunca equivale a cero.

    Los casos vienen del contexto congelado y son independientes del modelo.
    La comparación futura debe exigir el mismo conjunto y completitud.
    """
    expected, groups, truth = {}, {}, {}
    for case in cases:
        key = case_key(case)
        if key in expected:
            raise ValueError("Caso de evaluación duplicado")
        expected[key] = case
    for row in forecasts:
        key = case_key(row)
        if key not in expected or row["cutoff"] != expected[key]["cutoff"]:
            raise ValueError("Pronóstico fuera del protocolo de casos/corte")
        q = float(row["quantile"])
        group = groups.setdefault(key, {})
        if q not in quantiles or q in group:
            raise ValueError("Cuantil inesperado o duplicado")
        if row["status"] == "ok":
            value = float(row["prediction"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Predicción inválida")
        elif row["status"] == "insufficient_history" and row["prediction"] == "":
            value = None
        else:
            raise ValueError("Estado de predicción inválido")
        group[q] = value
    for row in actuals:
        key = row["date"], int(row["store_nbr"]), row["family"]
        if key not in expected:
            continue
        value = float(row["sales"])
        if key in truth or not math.isfinite(value) or value < 0:
            raise ValueError("Venta real duplicada o inválida")
        truth[key] = value
    metric = Accumulator(quantiles)
    pending_actual = unavailable_forecast = 0
    joined = []
    for key, case in sorted(expected.items()):
        predictions = groups.get(key, {})
        if predictions and set(predictions) != set(quantiles):
            raise ValueError("Conjunto incompleto de cuantiles")
        if any(v is None for v in predictions.values()) and any(v is not None for v in predictions.values()):
            raise ValueError("Disponibilidad inconsistente entre cuantiles")
        usable = bool(predictions) and all(v is not None for v in predictions.values())
        if usable and list(predictions[q] for q in quantiles) != sorted(predictions.values()):
            raise ValueError("Cuantiles cruzados")
        known = key in truth
        pending_actual += not known
        unavailable_forecast += not usable
        status = "scored" if known and usable else ("actual_pending" if not known else "forecast_unavailable")
        if status == "scored":
            for accumulator in [metric, *accumulators]:
                accumulator.add(truth[key], predictions)
        joined.append({**case, "actual": truth[key] if known else "", "status": status,
                       **{f"q{q:g}": predictions.get(q) if predictions.get(q) is not None else "" for q in quantiles}})
    return {**metric.summary(), "expected_cases": len(expected), "actual_pending_cases": pending_actual,
            "forecast_unavailable_cases": unavailable_forecast,
            "completion_fraction": metric.n / len(expected) if expected else None}, joined

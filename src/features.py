"""Variables históricas: nunca consultar valores posteriores al origen del ejemplo."""

import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from src.baseline import quantile
from src.deliveries import timestamp
from src.validate_snapshot import rows, validate

CATEGORIES = ["store_nbr", "family", "city", "state", "type", "cluster"]
NUMERIC = ["horizon", "target_weekday", "target_day", "target_month", "target_month_end", "target_payday",
           "scale_log1p", "baseline_low_ratio", "baseline_high_ratio", "last_sales_ratio", "mean7_ratio",
           "mean28_ratio", "std28_ratio", "weekday_mean_ratio", "count7", "count28", "weekday_count",
           "promo_mean7", "promo_last", "transactions_last_log1p", "transactions_mean7_log1p",
           "transactions_count7", "transactions_age", "oil_last", "oil_age", "calendar_events7", "calendar_known_days7"]
FEATURES = CATEGORIES + NUMERIC
CATEGORICAL_INDICES = list(range(len(CATEGORIES))) + [FEATURES.index("target_weekday")]


def mean(values):
    return statistics.fmean(values) if values else math.nan


class History:
    def __init__(self, snapshot):
        self.quality = validate(snapshot)
        manifest = json.loads((Path(snapshot) / "manifest.json").read_text())
        self.cutoff = timestamp(manifest["cutoff"])
        self.availability = {(r["entry"]["source"], r["entry"]["data_date"]): timestamp(r["entry"]["available_at"])
                             for r in manifest["selected"]}
        self.catalog_available = max((v for (source, _), v in self.availability.items() if source == "stores"), default=self.cutoff)
        self.stores = {int(r["store_nbr"]): r for r in rows(snapshot, "stores")}
        self.sales = defaultdict(list)
        self.labels = {}
        for row in rows(snapshot, "train"):
            key = int(row["store_nbr"]), row["family"]
            item = (date.fromisoformat(row["date"]), float(row["sales"]), int(row["onpromotion"]), self.availability["train", row["date"]])
            self.sales[key].append(item)
            self.labels[item[0], *key] = item[1]
        for values in self.sales.values():
            values.sort()
        self.families = sorted({family for _, family in self.sales})
        self.transactions = defaultdict(list)
        for row in rows(snapshot, "transactions"):
            self.transactions[int(row["store_nbr"])].append((date.fromisoformat(row["date"]), int(row["transactions"]),
                                                           self.availability["transactions", row["date"]]))
        for values in self.transactions.values():
            values.sort()
        self.oil = [(date.fromisoformat(r["date"]), float(r["dcoilwtico"]) if r["dcoilwtico"] else None,
                     self.availability["oil", r["date"]]) for r in rows(snapshot, "oil")]
        self.oil.sort()
        self.events = [(date.fromisoformat(r["date"]), r, self.availability["holidays_events", r["date"]])
                       for r in rows(snapshot, "holidays_events")]
        self.calendar = [(date.fromisoformat(d), t) for (source, d), t in self.availability.items() if source == "holidays_events"]
        values = {name: set() for name in CATEGORIES}
        for store in self.stores.values():
            for name in CATEGORIES:
                if name != "family":
                    values[name].add(str(store[name]))
        values["family"].update(self.families)
        self.category_maps = {name: {v: i for i, v in enumerate(sorted(items))} for name, items in values.items()}

    def feature(self, origin, target, store, family, baseline_config, ml_config):
        if origin > self.cutoff or not 1 <= (target - origin.date()).days <= ml_config["horizon_days"]:
            raise ValueError("Origen/objetivo fuera del contrato temporal")
        if store not in self.stores or origin < self.catalog_available:
            return None
        start = origin.date() - timedelta(days=baseline_config["lookback_days"])
        recent = [r for r in self.sales[store, family] if start <= r[0] < origin.date() and r[3] <= origin]
        weekday = [r for r in recent if r[0].weekday() == target.weekday()]
        chosen = weekday if len(weekday) >= baseline_config["min_weekday_observations"] else recent
        if (len(weekday) < baseline_config["min_weekday_observations"]
                and len(recent) < baseline_config["min_fallback_observations"]):
            return None
        if not chosen:
            return None
        reference = {q: quantile([r[1] for r in chosen], q) for q in ml_config["quantiles"]}
        center = reference[0.5]
        scale = max(center, mean([r[1] for r in recent]) * ml_config["scale_floor_fraction"], ml_config["minimum_scale"])
        first7 = origin.date() - timedelta(days=7)
        recent7 = [r for r in recent if r[0] >= first7]
        transactions = [r for r in self.transactions[store] if first7 <= r[0] < origin.date() and r[2] <= origin]
        oil = [r for r in self.oil if r[0] < origin.date() and r[2] <= origin and r[1] is not None]
        known_calendar = [(d, t) for d, t in self.calendar if first7 <= d < origin.date() and t <= origin]
        catalog = self.stores[store]
        events = [(d, r, t) for d, r, t in self.events if first7 <= d < origin.date() and t <= origin
                  and r["transferred"] != "True" and (r["locale"] == "National"
                  or (r["locale"] == "Regional" and r["locale_name"] == catalog["state"])
                  or (r["locale"] == "Local" and r["locale_name"] == catalog["city"]))]
        average = mean([r[1] for r in recent])
        deviation = math.sqrt(math.fsum((r[1]-average)**2 for r in recent)/len(recent))
        numeric = [(target-origin.date()).days, target.weekday(), target.day, target.month,
                   int((target+timedelta(days=1)).month != target.month), int(target.day == 15 or (target+timedelta(days=1)).month != target.month),
                   math.log1p(scale), reference[ml_config["quantiles"][0]]/scale, reference[ml_config["quantiles"][-1]]/scale,
                   recent[-1][1]/scale, mean([r[1] for r in recent7])/scale, mean([r[1] for r in recent])/scale,
                   deviation/scale, mean([r[1] for r in weekday])/scale,
                   len(recent7), len(recent), len(weekday), mean([r[2] for r in recent7]), recent[-1][2],
                   math.log1p(transactions[-1][1]) if transactions else math.nan,
                   math.log1p(mean([r[1] for r in transactions])) if transactions else math.nan, len(transactions),
                   (origin.date()-transactions[-1][0]).days if transactions else math.nan,
                   oil[-1][1] if oil else math.nan, (origin.date()-oil[-1][0]).days if oil else math.nan,
                   len(events) if known_calendar else math.nan, len(known_calendar)]
        values = {**catalog, "family": family}
        vector = [self.category_maps[name][str(values[name])] for name in CATEGORIES] + numeric
        used_times = [self.catalog_available, *[r[3] for r in recent], *[r[2] for r in transactions],
                      *([oil[-1][2]] if oil else []), *[r[2] for r in events], *[t for _, t in known_calendar]]
        latest = max(used_times)
        if latest > origin:
            raise ValueError("Fuga temporal en características")
        return {"vector": vector, "center": center, "scale": scale, "reference": reference,
                "history_count": len(chosen), "latest_feature_available_at": latest.isoformat()}

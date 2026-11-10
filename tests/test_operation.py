"""Flujo operativo completo con datos sintéticos: idempotencia, cuarentena, corrección,
backfill, publicaciones inmutables y seguimiento. No requiere Kaggle, Docker ni Airflow."""

import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src import operation
from src.deliveries import SCHEMAS, sha256

FAMILIES = ["A", "B"]
STORES = [1, 2]


def write_csv(path, source, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(SCHEMAS[source])
        writer.writerows(rows)


class OperationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        originals = self.root / "dataOriginal"
        originals.mkdir()
        (self.root / "config").mkdir()
        days = [date(2017, 1, 1) + timedelta(days=i) for i in range(25)]
        train, ident = [], 0
        for day in days:
            for store in STORES:
                for family in FAMILIES:
                    ident += 1
                    train.append([ident, day.isoformat(), store, family, 10 * store + day.day % 5, 0])
        write_csv(originals / "train.csv", "train", train)
        write_csv(originals / "stores.csv", "stores", [[s, "Quito", "Pichincha", "A", 1] for s in STORES])
        write_csv(originals / "transactions.csv", "transactions", [[d.isoformat(), s, 100] for d in days for s in STORES])
        write_csv(originals / "oil.csv", "oil", [[d.isoformat(), 50] for d in days])
        write_csv(originals / "holidays_events.csv", "holidays_events",
                  [["2017-01-01", "Holiday", "National", "Ecuador", "Nuevo año", "False"]])
        self.original_hashes = {f.name: sha256(f) for f in originals.iterdir()}
        (self.root / "config/baseline.json").write_text(json.dumps(
            {"horizon_days": 3, "lookback_days": 28, "quantiles": [0.1, 0.5, 0.9],
             "min_weekday_observations": 3, "min_fallback_observations": 7}))
        (self.root / "config/costs.json").write_text(json.dumps(
            {"schema_version": 1, "scenario_id": "test-9-1", "description": "prueba", "cost_basis": "illustrative_relative",
             "cost_unit": "relative_cost_unit", "defaults": {"shortage_per_unit": 9.0, "excess_per_unit": 1.0},
             "family_overrides": {}, "quantile_rule": "linear_interpolation_no_extrapolation",
             "quantity_type": "daily_supply_target"}))
        config = {"simulation": {
            "scenario_id": "op-test", "description": "sintético", "history_start": "2017-01-01",
            "history_end": "2017-01-15", "delivery_end": "auto", "availability_hour_utc": 12,
            "lag_days": {"train": 1, "stores": 0, "holidays_events": 1, "oil": 2, "transactions": 2},
            "delays": [{"source": "transactions", "data_date": "2017-01-17", "extra_days": 2}],
            "corrections": [{"source": "train", "data_date": "2017-01-17", "store_nbr": 1,
                             "preliminary_factor": 0.0, "correction_lag_days": 2}],
            "invalid_deliveries": [{"source": "oil", "data_date": "2017-01-16", "fix_lag_days": 1}]},
            "operation": {"start_date": "2017-01-16", "end_date": "2017-01-22", "cutoff_hour_utc": 13},
            "baseline_config": "config/baseline.json", "costs_config": "config/costs.json",
            "paths": {"originals": "dataOriginal", "inbox": "data/inbox", "ledger": "data/ledger.json",
                      "snapshots": "data/processed", "published": "data/published", "tracking": "data/tracking"}}
        path = self.root / "config/operacion.json"
        path.write_text(json.dumps(config))
        self.config = operation.load_config(path)
        self.created = operation.prepare_inbox(self.config)

    def run_days(self, days):
        return {d: operation.run_day(self.config, d) for d in days}

    def test_producer_is_idempotent_and_resolves_auto_end(self):
        self.assertEqual(self.created["delivery_end"], "2017-01-25")
        self.assertEqual(operation.prepare_inbox(self.config)["status"], "exists")
        changed = json.loads(json.dumps(self.config))
        changed["simulation"]["lag_days"]["train"] = 2
        with self.assertRaises(FileExistsError):
            operation.prepare_inbox(changed)

    def test_full_period_quarantine_correction_and_tracking(self):
        results = self.run_days(operation.operation_dates(self.config))
        # El oil inválido del 16 llega el 18 y queda en cuarentena; su r2 llega el 19.
        rejected = results["2017-01-18"]["ingest"]["rejected"]
        self.assertEqual([r["delivery_id"] for r in rejected], ["oil/2017-01-16/r1"])
        self.assertTrue(all(r["publish"]["status"] == "published" for r in results.values()))
        oil = (self.root / "data/processed/2017-01-19/oil.csv").read_text()
        self.assertIn("2017-01-16,50", oil)
        self.assertNotIn(",-1", (self.root / "data/processed/2017-01-18/oil.csv").read_text())
        # La venta preliminar (factor 0) se corrige el 20; el seguimiento lo refleja.
        early = json.loads((self.root / "data/tracking/2017-01-19/tracking.json").read_text())
        late = json.loads((self.root / "data/tracking/2017-01-20/tracking.json").read_text())
        self.assertEqual(early["corrections_applied"], [])
        self.assertEqual(late["corrections_applied"], ["train/2017-01-17/r2"])
        self.assertGreater(late["overall_technical"]["scored_cases"], 0)
        self.assertIn("# Seguimiento", (self.root / "data/tracking/2017-01-20/report.md").read_text())
        # Lo publicado nunca se reescribe: el corte del 18 conserva la venta preliminar.
        snap18 = (self.root / "data/processed/2017-01-18/train.csv").read_text()
        self.assertIn("2017-01-17,1,A,0.0", snap18)
        self.assertEqual({f.name: sha256(f) for f in (self.root / "dataOriginal").iterdir()}, self.original_hashes)

    def test_rerun_and_backfill_are_idempotent(self):
        days = operation.operation_dates(self.config)[:4]
        first = self.run_days(days)
        publication = Path(first[days[1]]["publish"]["publication"])
        before = {f.name: f.read_bytes() for f in publication.iterdir()}
        ledger = (self.root / "data/ledger.json").read_bytes()
        again = operation.run_day(self.config, days[1])  # backfill de un día pasado
        self.assertEqual(again["ingest"]["mode"], "backfill")
        self.assertEqual(again["publish"]["status"], "already_published")
        self.assertEqual({f.name: f.read_bytes() for f in publication.iterdir()}, before)
        self.assertEqual((self.root / "data/ledger.json").read_bytes(), ledger)
        tracking = (self.root / f"data/tracking/{days[3]}/tracking.json").read_bytes()
        operation.run_day(self.config, days[3])
        self.assertEqual((self.root / f"data/tracking/{days[3]}/tracking.json").read_bytes(), tracking)

    def test_cost_change_creates_new_publication_without_touching_old(self):
        day = "2017-01-16"
        old = Path(operation.run_day(self.config, day)["publish"]["publication"])
        costs = json.loads((self.root / "config/costs.json").read_text())
        costs["defaults"] = {"shortage_per_unit": 1.0, "excess_per_unit": 1.0}
        (self.root / "config/costs.json").write_text(json.dumps(costs))
        new = Path(operation.step_publish(self.config, day)["publication"])
        self.assertNotEqual(old, new)
        with (new / "orders.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({r["required_quantile"] for r in rows}, {"0.5"})
        self.assertTrue((old / "orders.csv").is_file())

    def test_past_publication_is_reproduced_exactly(self):
        self.run_days(operation.operation_dates(self.config)[:5])
        result = operation.reproduce(self.config, "2017-01-17")
        self.assertTrue(result["identical"], result)
        self.assertIn("forecast.csv", result["files"])

    def test_tampered_publication_is_detected(self):
        publication = Path(operation.run_day(self.config, "2017-01-16")["publish"]["publication"])
        (publication / "orders.csv").write_text("alterado")
        with self.assertRaises(FileExistsError):
            operation.step_publish(self.config, "2017-01-16")

    def test_missing_inbox_is_explicit(self):
        config = json.loads(json.dumps(self.config))
        config["paths"]["inbox"] = "data/no-existe"
        with self.assertRaisesRegex(FileNotFoundError, "bandeja"):
            operation.step_ingest(config, "2017-01-16")


if __name__ == "__main__":
    unittest.main()

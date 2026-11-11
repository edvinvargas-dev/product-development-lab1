import copy
import json
import unittest

from src.deliveries import json_bytes, sha256
from src.evaluation import evaluate_baseline, load_context, prepare, protocol, tree_hashes
from src.metrics import Accumulator, score
from src.deliveries import timestamp
from src.ingest import ingest, load_ledger
from src.replay import replay_knowledge
from test_temporal_ingestion import ScenarioFixture


def case(day="2017-01-03"):
    return {"cutoff": "2017-01-02T13:00:00+00:00", "target_date": day, "store_nbr": 1, "family": "A"}


def forecast(values=(8, 12, 14), day="2017-01-03"):
    return [{**case(day), "quantile": q, "prediction": v, "status": "ok"} for q, v in zip([0.1, 0.5, 0.9], values)]


class MetricsTests(unittest.TestCase):
    def test_hand_calculated_metrics(self):
        metric = Accumulator([0.1, 0.5, 0.9])
        metric.add(10, {0.1: 8, 0.5: 12, 0.9: 14})
        result = metric.summary()
        self.assertEqual(result["mae"], 2)
        self.assertEqual(result["rmse"], 2)
        self.assertEqual(result["wape"], 0.2)
        self.assertEqual(result["bias_prediction_minus_actual"], 2)
        self.assertAlmostEqual(result["mean_pinball"], (0.2 + 1 + 0.4) / 3)
        self.assertEqual(result["interval_coverage"], 1)
        self.assertEqual(result["mean_interval_width"], 6)

    def test_zero_denominator_and_no_cases_are_explicit(self):
        metric = Accumulator([0.1, 0.5, 0.9])
        self.assertIsNone(metric.summary()["mae"])
        metric.add(0, {0.1: 0, 0.5: 0, 0.9: 0})
        self.assertIsNone(metric.summary()["wape"])
        self.assertEqual(metric.summary()["mae"], 0)

    def test_missing_actual_is_pending_not_zero(self):
        result, joined = score([case()], forecast(), [], [0.1, 0.5, 0.9])
        self.assertEqual(result["actual_pending_cases"], 1)
        self.assertEqual(result["scored_cases"], 0)
        self.assertIsNone(result["mae"])
        self.assertEqual(joined[0]["actual"], "")

    def test_dropped_forecast_is_counted_against_fixed_case_set(self):
        actual = [{"date": "2017-01-03", "store_nbr": 1, "family": "A", "sales": 10}]
        result, _ = score([case()], [], actual, [0.1, 0.5, 0.9])
        self.assertEqual(result["expected_cases"], 1)
        self.assertEqual(result["forecast_unavailable_cases"], 1)
        self.assertEqual(result["completion_fraction"], 0)

    def test_invalid_crossed_duplicate_and_extra_forecasts_fail(self):
        for values in [forecast((10, 9, 14)), forecast() + forecast()[:1], forecast(day="2017-01-04")]:
            with self.assertRaises(ValueError):
                score([case()], values, [], [0.1, 0.5, 0.9])

    def test_partial_quantiles_cannot_be_scored_silently(self):
        values = forecast()
        values[0].update(prediction="", status="insufficient_history")
        with self.assertRaisesRegex(ValueError, "inconsistente"):
            score([case()], values, [], [0.1, 0.5, 0.9])

    def test_join_uses_key_not_csv_position_and_pools_by_case(self):
        actuals = [{"date": "2017-01-04", "store_nbr": 1, "family": "A", "sales": 0},
                   {"date": "2017-01-03", "store_nbr": 1, "family": "A", "sales": 10}]
        pooled = Accumulator([0.1, 0.5, 0.9])
        result, _ = score([case(), case("2017-01-04")], forecast() + forecast((0, 0, 0), "2017-01-04"),
                          actuals, [0.1, 0.5, 0.9], accumulators=[pooled])
        self.assertEqual(result["mae"], 1)
        self.assertEqual(result["scored_cases"], 2)
        self.assertEqual(result["mae"], pooled.summary()["mae"])


class TemporalEvaluationTests(ScenarioFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plan = {"evaluation_id": "synthetic-development-v1", "purpose": "development",
                     "poll_start": "2017-01-02T13:00:00Z", "as_of": "2017-01-05T13:00:00Z",
                     "poll_step_days": 1, "cutoffs": ["2017-01-02T13:00:00Z"],
                     "horizon_days": 1, "quantiles": [0.1, 0.5, 0.9]}
        self.baseline = {"horizon_days": 1, "lookback_days": 28, "quantiles": [0.1, 0.5, 0.9],
                         "min_weekday_observations": 1, "min_fallback_observations": 1}
        self.context = self.root / "context"

    def test_context_replay_and_results_are_identical_and_inputs_unchanged(self):
        before = self.hashes()
        prepare(self.inbox, self.plan, self.context)
        hashes = tree_hashes(self.context)
        prepare(self.inbox, self.plan, self.context)
        self.assertEqual(tree_hashes(self.context), hashes)
        ledger = json.loads((self.context / "logical_ledger.json").read_text())
        self.assertTrue(all("recorded_at_wall" not in r for r in ledger["receipts"]))
        result = evaluate_baseline(self.context, self.baseline, self.root / "evaluation")
        self.assertEqual(result["pooled"]["scored_cases"], 1)
        self.assertEqual(result["folds"][0]["training_date_max"], "2017-01-01")
        self.assertEqual(result["pooled"]["mae"], 99995)
        self.assertEqual(result, evaluate_baseline(self.context, self.baseline, self.root / "evaluation"))
        self.assertEqual(before, self.hashes())

    def test_fast_replay_matches_operational_polling_exactly(self):
        polling, _ = protocol(self.plan)
        journal = self.root / "operational.json"
        expected_polls = [ingest(self.inbox, journal, at.isoformat()) for at in polling]
        expected_ledger = load_ledger(journal)
        for receipt in expected_ledger["receipts"]:
            receipt.pop("recorded_at_wall")
        ledger, polls = replay_knowledge(self.inbox, polling)
        self.assertEqual(ledger, expected_ledger)
        self.assertEqual(polls, expected_polls)

    def test_fast_replay_keeps_missing_files_pending_and_does_not_read_future(self):
        (self.inbox / "train/2017-01-01/r1.csv").rename(self.root / "not-delivered.csv")
        # Datos aún no disponibles no deben validarse ni contaminar este replay.
        (self.inbox / "train/2017-01-03/r1.csv").write_text("future-corrupted")
        polling = [timestamp("2017-01-02T13:00:00Z")]
        ledger, polls = replay_knowledge(self.inbox, polling)
        self.assertEqual(polls[0]["awaiting_delivery"], [{"delivery_id": "train/2017-01-01/r1", "status": "awaiting_delivery"}])
        self.assertFalse(any(r["entry"]["source"] == "train" for r in ledger["receipts"]))

    def test_future_truth_correction_changes_score_without_changing_model(self):
        prepare(self.inbox, self.plan, self.context)
        first = evaluate_baseline(self.context, self.baseline, self.root / "evaluation")
        # El productor sintético corrige una venta del horizonte después de emitir.
        entry = copy.deepcopy(next(e for e in self.manifest["deliveries"] if e["delivery_id"] == "train/2017-01-03/r1"))
        entry.update(delivery_id="train/2017-01-03/r2", revision=2, path="train/2017-01-03/r2.csv",
                     available_at="2017-01-05T12:00:00+00:00")
        self.write_csv(self.inbox / entry["path"], "train", [[3, "2017-01-03", 1, "A", 20, 0]])
        entry["sha256"] = sha256(self.inbox / entry["path"])
        self.manifest["deliveries"].append(entry)
        self.save_manifest()
        revised_context = self.root / "context-revised"
        prepare(self.inbox, self.plan, revised_context)
        revised = evaluate_baseline(revised_context, self.baseline, self.root / "evaluation-revised")
        self.assertEqual(first["folds"][0]["model_id"], revised["folds"][0]["model_id"])
        self.assertEqual(revised["pooled"]["mae"], 15)
        self.assertNotEqual(first["context_manifest_sha256"], revised["context_manifest_sha256"])

    def test_late_actual_remains_pending_at_fixed_evaluation_close(self):
        entry = next(e for e in self.manifest["deliveries"] if e["delivery_id"] == "train/2017-01-03/r1")
        entry["available_at"] = "2017-01-06T12:00:00+00:00"
        self.save_manifest()
        prepare(self.inbox, self.plan, self.context)
        result = evaluate_baseline(self.context, self.baseline, self.root / "evaluation")
        self.assertEqual(result["actual_pending_cases"], 1)
        self.assertIsNone(result["pooled"]["mae"])

    def test_tampered_context_and_different_horizon_are_rejected(self):
        prepare(self.inbox, self.plan, self.context)
        with self.assertRaisesRegex(ValueError, "idénticos"):
            evaluate_baseline(self.context, dict(self.baseline, horizon_days=7), self.root / "evaluation")
        path = self.context / "folds/2017-01-02/cases.csv"
        path.write_text("alterado")
        with self.assertRaisesRegex(ValueError, "alterad"):
            load_context(self.context)

    def test_overlapping_or_off_schedule_cuts_are_rejected(self):
        for change in [dict(cutoffs=["2017-01-02T14:00:00Z"]),
                       dict(cutoffs=["2017-01-02T13:00:00Z", "2017-01-03T13:00:00Z"], horizon_days=7)]:
            with self.assertRaises(ValueError):
                protocol({**self.plan, **change})


if __name__ == "__main__":
    unittest.main()

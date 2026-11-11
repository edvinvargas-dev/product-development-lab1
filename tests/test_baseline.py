import copy
import json
import unittest

from src.baseline import checked_config, fit, model_identifier, predict, publish, quantile
from src.deliveries import json_bytes, sha256
from src.ingest import ingest
from src.validate_snapshot import validate
from test_temporal_ingestion import ScenarioFixture


class QuantileTests(unittest.TestCase):
    def test_interpolation_and_extremes_are_retained(self):
        self.assertEqual(quantile([30, 10, 20], 0.1), 12)
        self.assertEqual(quantile([0, 100000], 0.9), 90000)
        self.assertEqual(quantile([0], 0.5), 0)

    def test_invalid_config_and_sample_fail(self):
        with self.assertRaises(ValueError):
            quantile([], 0.5)
        with self.assertRaises(ValueError):
            checked_config({})
        config = {"horizon_days": 7, "lookback_days": 28, "quantiles": [0.9, 0.1],
                  "min_weekday_observations": 3, "min_fallback_observations": 7}
        with self.assertRaises(ValueError):
            checked_config(config)


class BaselineTests(ScenarioFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.at = "2017-01-03T13:00:00Z"
        ingest(self.inbox, self.ledger, self.at)
        self.cut(self.at, "known")
        self.known = self.root / "snapshots/known"
        self.config = {"horizon_days": 7, "lookback_days": 28, "quantiles": [0.1, 0.5, 0.9],
                       "min_weekday_observations": 3, "min_fallback_observations": 2}

    def test_forecast_uses_known_history_and_targets_only_next_seven_days(self):
        model, report = fit(self.known, self.config)
        forecasts = list(predict(model))
        self.assertEqual(report["status"], "ready")
        self.assertEqual(model["training_date_max"], "2017-01-02")
        self.assertEqual(model["training_rows"], 2)
        self.assertEqual(len(forecasts), 21)
        self.assertEqual(forecasts[0]["target_date"], "2017-01-04")
        self.assertEqual(forecasts[-1]["target_date"], "2017-01-10")
        # La venta futura de 100000 del día 3 no interviene; se usan 5 y 0.
        self.assertEqual([r["prediction"] for r in forecasts[:3]], [0.5, 2.5, 4.5])
        self.assertEqual(forecasts[0]["method"], "all_weekdays_fallback")
        self.assertGreater(report["store_dates_without_transactions"], 0)
        self.assertEqual(model, fit(self.known, self.config)[0])

    def test_same_weekday_has_priority_when_enough_observations(self):
        config = dict(self.config, min_weekday_observations=1)
        model, _ = fit(self.known, config)
        result = next(r for r in predict(model) if r["target_date"] == "2017-01-08")
        self.assertEqual(result["method"], "same_weekday")
        self.assertEqual(result["prediction"], 5)

    def test_cold_start_is_explicit_and_not_zero(self):
        model, _ = fit(self.known, dict(self.config, min_fallback_observations=7))
        for row in predict(model):
            self.assertEqual(row["status"], "insufficient_history")
            self.assertEqual(row["prediction"], "")

    def test_lookback_is_anchored_to_cutoff_and_keeps_zeros(self):
        model, _ = fit(self.known, dict(self.config, lookback_days=1, min_weekday_observations=1))
        self.assertEqual(model["training_date_min"], "2017-01-02")
        self.assertEqual(model["training_rows"], 1)
        result = next(r for r in predict(model) if r["target_date"] == "2017-01-09")
        self.assertEqual(result["prediction"], 0)

    def test_snapshot_tampering_and_unknown_store_are_invalid(self):
        path = self.known / "train.csv"
        path.write_text(path.read_text().replace(",1,A,", ",999,A,"))
        with self.assertRaisesRegex(ValueError, "Hash"):
            validate(self.known)
        manifest_path = self.known / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["outputs_sha256"]["train"] = sha256(path)
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "Tienda desconocida"):
            validate(self.known)

    def test_missing_input_waits_without_inventing_model(self):
        self.cut("2017-01-01T13:00:00Z", "empty")
        model, report = fit(self.root / "snapshots/empty", self.config)
        self.assertIsNone(model)
        self.assertEqual(report["status"], "not_ready")

    def test_model_integrity_and_immutable_publication(self):
        model, _ = fit(self.known, self.config)
        altered = copy.deepcopy(model)
        altered["cutoff"] = "2017-01-04T13:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "Identificador"):
            list(predict(altered))
        self.assertEqual(model_identifier(model), model["model_id"])
        dest = self.root / "publication"
        files = {"model.json": json_bytes(model)}
        publish(dest, files, self.known)
        before = (dest / "model.json").read_bytes()
        publish(dest, files, self.known)
        with self.assertRaises(FileExistsError):
            publish(dest, {"model.json": b"different"}, self.known)
        self.assertEqual((dest / "model.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

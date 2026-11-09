"""Casos temporales con datos sintéticos: no dependen de Kaggle ni de Docker."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.deliveries import SCHEMAS, json_bytes, sha256, timestamp
from src.ingest import ingest
from src.simulate import generate
from src.snapshot import snapshot


class ScenarioFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.originals = self.root / "originals"
        self.originals.mkdir()
        self.inbox, self.ledger = self.root / "inbox", self.root / "state" / "ledger.json"
        self.config = {"scenario_id": "synthetic-test-v1", "history_start": "2017-01-01",
                       "history_end": "2017-01-01", "delivery_end": "2017-01-03",
                       "availability_hour_utc": 12,
                       "lag_days": {"train": 1, "stores": 0, "oil": 2, "transactions": 2, "holidays_events": 1},
                       "delays": [{"source": "transactions", "data_date": "2017-01-02", "extra_days": 2}]}
        rows = {
            "stores": [[1, "Quito", "Pichincha", "A", 1]],
            "train": [[i, f"2017-01-0{i}", 1, "A", v, 0] for i, v in [(1, 5), (2, 0), (3, 100000)]],
            "transactions": [[f"2017-01-0{i}", 1, 10] for i in range(1, 4)],
            "oil": [["2017-01-01", ""], ["2017-01-03", 50]],
            "holidays_events": [["2017-01-01", "Holiday", "National", "Ecuador", "Nuevo año", "False"]],
        }
        for source, values in rows.items():
            self.write_csv(self.originals / f"{source}.csv", source, values)
        self.original_hashes = {p.name: sha256(p) for p in self.originals.iterdir()}
        self.manifest = generate(self.originals, self.inbox, self.config)

    def write_csv(self, path, source, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(SCHEMAS[source])
            writer.writerows(rows)

    def hashes(self):
        return {str(p.relative_to(self.inbox)): sha256(p) for p in self.inbox.rglob("*") if p.is_file()}

    def save_manifest(self):
        (self.inbox / "manifest.json").write_bytes(json_bytes(self.manifest))

    def cut(self, at, name):
        return snapshot(self.inbox, self.ledger, at, self.root / "snapshots" / name)


class TemporalIngestionTests(ScenarioFixture, unittest.TestCase):
    def test_future_values_are_excluded_and_retry_does_not_write(self):
        before = self.hashes()
        at = "2017-01-02T13:00:00Z"
        first = ingest(self.inbox, self.ledger, at)
        ledger_before = self.ledger.read_bytes()
        self.assertEqual(first["new_deliveries"], 3)
        self.assertEqual(ingest(self.inbox, self.ledger, at)["new_deliveries"], 0)
        self.assertEqual(self.ledger.read_bytes(), ledger_before)
        result = self.cut(at, "first")
        self.assertEqual(result["sources"]["train"]["rows"], 1)
        self.assertEqual(result["sources"]["train"]["latest_data_date"], "2017-01-01")
        self.assertEqual(result["sources"]["oil"]["status"], "not_available")
        self.assertEqual(result, self.cut(at, "first"))
        self.assertEqual(self.hashes(), before)
        self.assertEqual({p.name: sha256(p) for p in self.originals.iterdir()}, self.original_hashes)

    def test_late_arrival_empty_delivery_and_null_price_are_explicit(self):
        ingest(self.inbox, self.ledger, "2017-01-05T13:00:00Z")
        early = self.cut("2017-01-05T13:00:00Z", "early")
        self.assertEqual(early["sources"]["transactions"]["rows"], 2)
        self.assertEqual(early["sources"]["oil"]["empty_dates"], ["2017-01-02"])
        # Precio faltante se conserva, no se transforma en cero ni se interpola.
        text = (self.root / "snapshots/early/oil.csv").read_text()
        self.assertIn("2017-01-01,\n", text)
        ingest(self.inbox, self.ledger, "2017-01-06T13:00:00Z")
        late = self.cut("2017-01-06T13:00:00Z", "late")
        self.assertEqual(late["sources"]["transactions"]["rows"], 3)

    def test_availability_alone_is_not_ingestion(self):
        ingest(self.inbox, self.ledger, "2017-01-03T13:00:00Z")
        past = self.cut("2017-01-02T13:00:00Z", "past")
        self.assertEqual(past["sources"]["train"]["status"], "not_available")
        with self.assertRaisesRegex(ValueError, "retroceder"):
            ingest(self.inbox, self.ledger, "2017-01-02T13:00:00Z")

    def test_correction_changes_new_cut_and_preserves_old_snapshot(self):
        at = "2017-01-02T13:00:00Z"
        ingest(self.inbox, self.ledger, at)
        old = self.cut(at, "published")
        entry = dict(next(e for e in self.manifest["deliveries"] if e["delivery_id"] == "train/2017-01-01/r1"))
        entry.update(revision=2, delivery_id="train/2017-01-01/r2", path="train/2017-01-01/r2.csv",
                     available_at="2017-01-04T12:00:00+00:00")
        self.write_csv(self.inbox / entry["path"], "train", [[1, "2017-01-01", 1, "A", 8, 0]])
        entry["sha256"] = sha256(self.inbox / entry["path"])
        self.manifest["deliveries"].append(entry)
        self.save_manifest()  # Acción del productor externo sintético, nunca de ingest/snapshot.
        frozen = self.hashes()
        ingest(self.inbox, self.ledger, "2017-01-04T13:00:00Z")
        self.assertEqual(old, self.cut(at, "published"))
        current = self.cut("2017-01-04T13:00:00Z", "corrected")
        self.assertIn("train/2017-01-01/r2", [r["entry"]["delivery_id"] for r in current["selected"]])
        self.assertIn("2017-01-01,1,A,8,0", (self.root / "snapshots/corrected/train.csv").read_text())
        self.assertEqual(self.hashes(), frozen)
        with self.assertRaises(FileExistsError):
            self.cut("2017-01-04T13:00:00Z", "published")

    def test_invalid_batch_does_not_partially_update_ledger(self):
        ingest(self.inbox, self.ledger, "2017-01-02T13:00:00Z")
        before = self.ledger.read_bytes()
        entry = next(e for e in self.manifest["deliveries"] if e["delivery_id"] == "train/2017-01-02/r1")
        (self.inbox / entry["path"]).write_text("corrupto")
        with self.assertRaisesRegex(ValueError, "Hash"):
            ingest(self.inbox, self.ledger, "2017-01-03T13:00:00Z")
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_invalid_values_and_duplicates_fail_even_with_correct_hash(self):
        entry = next(e for e in self.manifest["deliveries"] if e["delivery_id"] == "train/2017-01-01/r1")
        for rows in [[[1, "2017-01-01", 1, "A", "nan", 0]],
                     [[1, "2017-01-01", 1, "A", 2, 0], [2, "2017-01-01", 1, "A", 3, 0]]]:
            self.write_csv(self.inbox / entry["path"], "train", rows)
            entry.update(sha256=sha256(self.inbox / entry["path"]), row_count=len(rows))
            self.save_manifest()
            with self.assertRaises(ValueError):
                ingest(self.inbox, self.ledger, "2017-01-02T13:00:00Z")
            self.assertFalse(self.ledger.exists())

    def test_producer_refuses_overwrite_and_consumer_refuses_write_to_inbox(self):
        before = self.hashes()
        with self.assertRaises(FileExistsError):
            generate(self.originals, self.inbox, self.config)
        with self.assertRaises(ValueError):
            ingest(self.inbox, self.inbox / "ledger.json", "2017-01-02T13:00:00Z")
        self.assertEqual(self.hashes(), before)

    def test_manifest_paths_cannot_escape_inbox(self):
        self.manifest["deliveries"][0]["path"] = "../outside.csv"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "dentro"):
            ingest(self.inbox, self.ledger, "2017-01-02T13:00:00Z")

    def test_missing_unseen_file_is_pending_but_removing_ingested_file_fails(self):
        path = self.inbox / "train/2017-01-01/r1.csv"
        held = self.root / "not-yet-delivered.csv"
        path.rename(held)  # Productor externo simula que el archivo todavía no llegó.
        result = ingest(self.inbox, self.ledger, "2017-01-02T13:00:00Z")
        self.assertEqual(result["awaiting_delivery"], [{"delivery_id": "train/2017-01-01/r1", "status": "awaiting_delivery"}])
        held.rename(path)
        self.assertEqual(ingest(self.inbox, self.ledger, "2017-01-03T13:00:00Z")["awaiting_delivery"], [])
        self.assertEqual(self.cut("2017-01-02T13:00:00Z", "before-arrival")["sources"]["train"]["rows"], 0)
        path.rename(held)
        with self.assertRaises(FileNotFoundError):
            ingest(self.inbox, self.ledger, "2017-01-03T13:00:00Z")

    def test_naive_timestamp_is_rejected_and_offsets_compare_in_utc(self):
        with self.assertRaisesRegex(ValueError, "zona"):
            timestamp("2017-01-02T13:00:00")
        self.assertEqual(timestamp("2017-01-02T08:00:00-05:00"), timestamp("2017-01-02T13:00:00Z"))


if __name__ == "__main__":
    unittest.main()

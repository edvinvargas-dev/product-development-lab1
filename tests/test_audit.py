"""Pruebas compatibles con unittest y pytest, usando datos sintéticos."""

import csv
import tempfile
import unittest
from pathlib import Path

from src.audit import audit_train


class AuditTests(unittest.TestCase):
    def audit(self, rows, chunk_size=1):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "train.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", "date", "store_nbr", "family", "sales", "onpromotion"])
                writer.writerows(rows)
            before = path.read_bytes()
            result = audit_train(path, chunk_size)
            self.assertEqual(path.read_bytes(), before)
            return result

    def test_maximum_is_not_sum_and_result_does_not_depend_on_blocks(self):
        rows = [[1, "2017-01-01", 1, "A", 7, 0], [2, "2017-01-02", 1, "A", 9, 0]]
        result = self.audit(rows)
        self.assertEqual(result["by_family"]["A"]["sales_max"], 9)
        self.assertEqual(result, self.audit(rows, chunk_size=10))

    def test_duplicate_across_blocks_and_calendar_gap(self):
        result = self.audit([[1, "2017-01-01", 1, "A", 0, 0],
                             [2, "2017-01-03", 1, "A", 4, 0],
                             [3, "2017-01-01", 1, "A", 0, 0]])
        self.assertEqual(result["duplicate_keys"], 1)
        self.assertEqual(result["missing_days"], ["2017-01-02"])
        self.assertEqual(result["missing_combinations_by_day"], {"2017-01-02": 1})
        self.assertEqual(result["zero_sales"], 2)

    def test_zero_and_extreme_are_preserved(self):
        result = self.audit([[1, "2017-01-01", 1, "A", 0, 0],
                             [2, "2017-01-01", 2, "A", 124717, 0]])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["sales_max"], 124717)

    def test_nonfinite_sales_stop_audit(self):
        with self.assertRaisesRegex(ValueError, "inválida"):
            self.audit([[1, "2017-01-01", 1, "A", "nan", 0]])


if __name__ == "__main__":
    unittest.main()

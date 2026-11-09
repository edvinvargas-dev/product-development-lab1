import copy
import importlib.util
import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.baseline import fit, predict
from src.deliveries import sha256, timestamp
from src.features import FEATURES, History
from src.ingest import ingest
from src.ml import fit_ml, load_ml, predict_ml, training_data
from src.selection import compare
from src.simulate import generate
from src.snapshot import snapshot
from test_temporal_ingestion import ScenarioFixture


class MLFixture(ScenarioFixture):
    def setUp(self):
        super().setUp()
        self.inbox = self.root/"ml-inbox"
        self.config.update(history_end="2017-01-10", delivery_end="2017-01-30",
                           delays=[{"source": "transactions", "data_date": "2017-01-10", "extra_days": 2}])
        self.write_csv(self.originals/"train.csv", "train",
                       [[d*10+s, f"2017-01-{d:02}", s, "A", (d%7)*3+s if d%5 else 0, d]
                        for d in range(1,31) for s in [1,2]])
        self.write_csv(self.originals/"stores.csv", "stores", [[s,"Quito","Pichincha","A",1] for s in [1,2]])
        self.write_csv(self.originals/"transactions.csv", "transactions",
                       [[f"2017-01-{d:02}",s,100+d] for d in range(1,31) for s in [1,2]])
        self.write_csv(self.originals/"oil.csv", "oil", [[f"2017-01-{d:02}",50+d] for d in range(1,31)])
        self.write_csv(self.originals/"holidays_events.csv", "holidays_events",
                       [["2017-01-07","Holiday","National","Ecuador","Sintético","False"]])
        generate(self.originals,self.inbox,self.config)
        self.at="2017-01-26T13:00:00Z"
        ledger=self.root/"ml-ledger.json"
        ingest(self.inbox,ledger,self.at)
        self.known=self.root/"ml-snapshot"
        snapshot(self.inbox,ledger,self.at,self.known)
        self.baseline=json.loads(Path("config/baseline.json").read_text())
        self.ml=json.loads(Path("config/ml.json").read_text())
        self.ml.update(max_iter=3,min_samples_leaf=2,minimum_training_history_days=7)


class FeatureTests(MLFixture,unittest.TestCase):
    def test_availability_and_all_sources_are_used_without_future(self):
        history=History(self.known)
        origin=timestamp("2017-01-12T13:00:00Z")
        result=history.feature(origin,date(2017,1,13),1,"A",self.baseline,self.ml)
        values=dict(zip(FEATURES,result["vector"]))
        self.assertEqual(values["promo_last"],11)
        self.assertAlmostEqual(values["transactions_last_log1p"],math.log1p(109))
        self.assertEqual(values["oil_last"],60)
        self.assertEqual(values["calendar_events7"],1)
        self.assertEqual(values["calendar_known_days7"],7)
        self.assertLessEqual(timestamp(result["latest_feature_available_at"]),origin)
        changed=copy.deepcopy(history)
        changed.sales[1,"A"]=[(d,999999,999999,a) if d>=origin.date() else (d,v,p,a)
                               for d,v,p,a in changed.sales[1,"A"]]
        again=changed.feature(origin,date(2017,1,13),1,"A",self.baseline,self.ml)
        self.assertEqual(result,again)

    def test_future_correction_and_missing_values_are_not_backfilled(self):
        history=History(self.known)
        origin=timestamp("2017-01-12T13:00:00Z")
        history.sales[1,"A"]=[(d,v,p,timestamp("2017-01-20T12:00:00Z")) if d==date(2017,1,8) else (d,v,p,a)
                              for d,v,p,a in history.sales[1,"A"]]
        first=history.feature(origin,date(2017,1,13),1,"A",self.baseline,self.ml)
        history.sales[1,"A"]=[(d,100000,p,a) if d==date(2017,1,8) else (d,v,p,a) for d,v,p,a in history.sales[1,"A"]]
        self.assertEqual(first,history.feature(origin,date(2017,1,13),1,"A",self.baseline,self.ml))
        history.oil=[];history.transactions[1]=[]
        result=history.feature(origin,date(2017,1,13),1,"A",self.baseline,self.ml)
        values=dict(zip(FEATURES,result["vector"]))
        self.assertTrue(math.isnan(values["oil_last"]))
        self.assertTrue(math.isnan(values["transactions_last_log1p"]))
        self.assertEqual(values["transactions_count7"],0)


@unittest.skipUnless(importlib.util.find_spec("sklearn"),"Requiere la imagen ml")
class LearnerTests(MLFixture,unittest.TestCase):
    def test_training_reload_determinism_median_and_temporal_lineage(self):
        history=History(self.known)
        X,y,weights,index=training_data(history,self.baseline,self.ml)
        self.assertGreater(len(y),4)
        for row in index:
            self.assertLessEqual(timestamp(row["latest_feature_available_at"]),timestamp(row["origin"]))
            self.assertLess(row["origin"][:10],row["target_date"])
            self.assertLess(row["target_date"],history.cutoff.date().isoformat())
            self.assertLessEqual(timestamp(row["label_available_at"]),history.cutoff)
        left,_=fit_ml(self.known,self.baseline,self.ml,self.root/"model-a")
        right,_=fit_ml(self.known,self.baseline,self.ml,self.root/"model-b")
        self.assertEqual(left,right)
        self.assertEqual(sha256(self.root/"model-a/model.pkl"),sha256(self.root/"model-b/model.pkl"))
        base,_=fit(self.known,self.baseline)
        baseline=list(predict(base))
        cases=[{k:r[k] for k in ["cutoff","target_date","store_nbr","family"]} for r in baseline if r["quantile"]==0.5]
        predictions=list(predict_ml(self.root/"model-a",self.known,cases))
        self.assertEqual([r["prediction"] for r in baseline if r["quantile"]==0.5],
                         [r["prediction"] for r in predictions if r["quantile"]==0.5])
        for i in range(0,len(predictions),3):
            values=[r["prediction"] for r in predictions[i:i+3]]
            self.assertEqual(values,sorted(values));self.assertGreaterEqual(values[0],0)
        path=self.root/"model-a/model.pkl";path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError,"alterado"):
            load_ml(self.root/"model-a")


class SelectionTests(unittest.TestCase):
    def reports(self):
        report={"evaluation_id":"test","purpose":"development","context_manifest_sha256":"same","as_of":"same",
                "baseline_config":{},"expected_cases":4,"actual_pending_cases":0,"forecast_unavailable_cases":0,
                "model":"baseline","pooled":{"scored_cases":4,"mean_pinball":10,"mae":5,"interval_coverage":0.6,"nominal_interval_coverage":0.8},
                "folds":[{"cutoff":str(i),"cases_sha256":str(i),"expected_cases":1,"scored_cases":1,"mean_pinball":10} for i in range(4)]}
        candidate=copy.deepcopy(report);candidate["model"]="candidate"
        candidate["pooled"].update(mean_pinball=8,interval_coverage=0.78)
        for fold in candidate["folds"]:fold["mean_pinball"]=8
        return report,candidate,json.loads(Path("config/model-selection.json").read_text())

    def test_technical_win_does_not_promote_without_costs_and_holdout(self):
        baseline,candidate,policy=self.reports()
        result=compare(baseline,candidate,policy)
        self.assertTrue(result["technical_pass"])
        self.assertAlmostEqual(result["relative_pinball_improvement"],0.2)
        self.assertFalse(result["production_promotion"])

    def test_cases_missing_predictions_and_worse_median_cannot_win(self):
        baseline,candidate,policy=self.reports()
        changed=copy.deepcopy(candidate);changed["folds"][0]["cases_sha256"]="different"
        with self.assertRaises(ValueError):compare(baseline,changed,policy)
        for change in [dict(mae=6),dict(scored_cases=3)]:
            changed=copy.deepcopy(candidate);changed["pooled"].update(change)
            self.assertFalse(compare(baseline,changed,policy)["technical_pass"])

    def test_perfect_baseline_does_not_divide_by_zero(self):
        baseline,candidate,policy=self.reports();baseline["pooled"]["mean_pinball"]=0
        self.assertFalse(compare(baseline,candidate,policy)["technical_pass"])


if __name__=="__main__":unittest.main()

import copy
import csv
import json
import unittest
from pathlib import Path

from src.orders import asymmetric_cost, build, choose_quantile, recommendations, score_orders, validate_costs
from src.business_evaluation import evaluate as evaluate_business
from src.evaluation import prepare, evaluate_baseline, tree_hashes
from test_temporal_ingestion import ScenarioFixture


def forecasts(family="A"):
    return [{"cutoff":"2017-01-01T13:00:00Z","target_date":"2017-01-02","store_nbr":1,"family":family,
             "model_id":"synthetic-model","quantile":q,"prediction":v,"status":"ok"}
            for q,v in [(0.1,2),(0.5,10),(0.9,18)]]


class OrdersTests(unittest.TestCase):
    def setUp(self):
        self.costs=json.loads(Path("config/examples/costs-relative-9-1.json").read_text())

    def test_cost_change_changes_quantity_without_logic_change(self):
        high=recommendations(forecasts(),self.costs)[0]
        balanced=copy.deepcopy(self.costs);balanced["defaults"]["shortage_per_unit"]=1
        low=recommendations(forecasts(),balanced)[0]
        self.assertEqual(high["target_quantity"],18)
        self.assertEqual(low["target_quantity"],10)
        self.assertNotEqual(high["decision_id"],low["decision_id"])
        self.assertIsNone(high["net_order_quantity"])
        self.assertEqual(high["inventory_status"],"not_provided")

    def test_family_override_and_interpolation(self):
        self.costs["family_overrides"]["A"]={"shortage_per_unit":3,"excess_per_unit":1}
        row=recommendations(forecasts(),self.costs)[0]
        self.assertEqual(row["required_quantile"],0.75)
        self.assertEqual(row["target_quantity"],15)
        self.assertEqual(row["quantile_method"],"linear_interpolation")
        self.assertEqual(recommendations(forecasts("B"),self.costs)[0]["target_quantity"],18)

    def test_unconfigured_and_unsupported_costs_are_explicit(self):
        config=json.loads(Path("config/costs.json").read_text())
        # La prueba usa una configuración pendiente independiente de la elección del usuario.
        config.update(cost_basis="not_configured",family_overrides={},defaults={"shortage_per_unit":None,"excess_per_unit":None})
        row=recommendations(forecasts(),config)[0]
        self.assertEqual(row["status"],"costs_not_configured");self.assertIsNone(row["target_quantity"])
        self.costs["defaults"]["shortage_per_unit"]=99
        row=recommendations(forecasts(),self.costs)[0]
        self.assertEqual(row["status"],"quantile_not_supported");self.assertIsNone(row["target_quantity"])

    def test_zeros_fractions_and_missing_forecasts_are_preserved(self):
        rows=forecasts()
        for row in rows:row["prediction"]=0.25
        self.assertEqual(recommendations(rows,self.costs)[0]["target_quantity"],0.25)
        for row in rows:row["prediction"]=0
        self.assertEqual(recommendations(rows,self.costs)[0]["target_quantity"],0)
        for row in rows:row.update(prediction="",status="insufficient_history")
        self.assertEqual(recommendations(rows,self.costs)[0]["status"],"forecast_unavailable")

    def test_invalid_costs_and_crossed_or_duplicate_quantiles_fail(self):
        for value in [-1,float("nan"),True]:
            config=copy.deepcopy(self.costs);config["defaults"]["shortage_per_unit"]=value
            with self.assertRaises(ValueError):validate_costs(config)
        for rows in [forecasts()+forecasts()[:1],forecasts()]:
            if len(rows)==3:rows[-1]["prediction"]=1
            with self.assertRaises(ValueError):recommendations(rows,self.costs)

    def test_hand_computed_cost_and_pinball_equivalence(self):
        self.assertEqual(asymmetric_cost(12,10,9,1),(2,0,18))
        self.assertEqual(asymmetric_cost(8,10,9,1),(0,2,2))
        for actual in [0,8,12,1000]:
            residual=actual-10
            pinball=max(0.9*residual,(0.9-1)*residual)
            self.assertAlmostEqual(asymmetric_cost(actual,10,9,1)[2],10*pinball)

    def test_pending_actual_is_not_zero_and_joins_use_case_keys(self):
        orders=recommendations(forecasts(),self.costs)
        report,_=score_orders(orders,[])
        self.assertEqual(report["actual_pending_cases"],1);self.assertIsNone(report["mean_proxy_cost"])
        actual={"cutoff":orders[0]["cutoff"],"target_date":"2017-01-02","store_nbr":1,"family":"A","actual":0}
        report,_=score_orders(orders,[actual])
        self.assertEqual(report["mean_proxy_cost"],18)


class OrderArtifactTests(ScenarioFixture,unittest.TestCase):
    def test_retries_are_identical_and_inputs_not_overwritten(self):
        folder=self.root/"forecast-input";folder.mkdir()
        path=folder/"forecast.csv"
        rows=forecasts()
        with path.open("w",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        config=json.loads(Path("config/examples/costs-relative-9-1.json").read_text())
        output=self.root/"orders";before=path.read_bytes()
        self.assertEqual(build(path,config,output),build(path,config,output))
        self.assertEqual(before,path.read_bytes())
        changed=copy.deepcopy(config);changed["defaults"]["shortage_per_unit"]=1
        with self.assertRaises(FileExistsError):build(path,changed,output)

    def test_business_evaluation_shares_truth_cases_and_is_reproducible(self):
        plan={"evaluation_id":"orders-test","purpose":"development","poll_start":"2017-01-02T13:00:00Z",
              "as_of":"2017-01-05T13:00:00Z","poll_step_days":1,"cutoffs":["2017-01-02T13:00:00Z"],
              "horizon_days":1,"quantiles":[0.1,0.5,0.9]}
        context=self.root/"context";prepare(self.inbox,plan,context)
        config={"horizon_days":1,"lookback_days":28,"quantiles":[0.1,0.5,0.9],
                "min_weekday_observations":1,"min_fallback_observations":1}
        base,candidate=self.root/"base",self.root/"candidate"
        evaluate_baseline(context,config,base);evaluate_baseline(context,config,candidate)
        costs=json.loads(Path("config/examples/costs-relative-9-1.json").read_text())
        frozen=tree_hashes(context)
        result=evaluate_business(context,base,candidate,costs,self.root/"business")
        self.assertEqual(result["models"]["baseline"]["pooled"]["mean_proxy_cost"],899955)
        self.assertTrue(result["comparison"]["identical_complete_cases"])
        self.assertEqual(result["comparison"]["relative_proxy_cost_improvement"],0)
        self.assertFalse(result["comparison"]["production_promotion"])
        self.assertEqual(result,evaluate_business(context,base,candidate,costs,self.root/"business"))
        self.assertEqual(tree_hashes(context),frozen)

    def test_decision_cannot_use_real_sales_to_choose_quantity(self):
        costs=json.loads(Path("config/examples/costs-relative-9-1.json").read_text())
        orders=recommendations(forecasts(),costs)
        before=copy.deepcopy(orders)
        for actual in [0,100000]:
            score_orders(orders,[{"cutoff":orders[0]["cutoff"],"target_date":"2017-01-02","store_nbr":1,
                                  "family":"A","actual":actual}])
            self.assertEqual(orders,before)


if __name__=="__main__":unittest.main()

"""A trained fixture proves wiring; it is not a production fault model."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from backend.app import checks
from backend.app.aggregator.aggregator import run_aggregator
from backend.app.main import app
from backend.app.ml.fault_model import FEATURES, FaultModel, fault_model
from backend.app.models import AggregatorInput, Case, CheckName, CreateCaseRequest
from backend.app.routers import cases


def case_for(party="RIDER", complaint="late"):
    ready, pickup, drop = ("12:50", "12:52", "13:10") if party == "MERCHANT" else ("12:12", "12:15", "13:20")
    if party == "NEITHER":
        drop = "12:30"
    timestamp = lambda t: f"2026-09-12T{t}:00+00:00"
    return Case.model_validate({
        "case_id": "test-" + party, "trigger": "customer_complaint",
        "order": {"id": "order-1", "status": "delivered", "zone_id": "z", "items": [],
                  "promised_prep_minutes": 10, "promised_delivery_minutes": 30,
                  "timestamps": {"placed_at": timestamp("12:00"), "prep_started_at": timestamp("12:00"),
                                 "ready_at": timestamp(ready), "picked_up_at": timestamp(pickup), "dropped_off_at": timestamp(drop)}},
        "merchant": {"id": "m", "name": "M", "zone_id": "z", "lat": 6.9, "lng": 79.8, "avg_prep_minutes": 10},
        "customer": {"id": "c", "name": "C", "address": "test", "lat": 6.91, "lng": 79.81},
        "rider_gps_trail": [
            {"lat": 6.9, "lng": 79.8, "recorded_at": timestamp(pickup)},
            {"lat": 6.9, "lng": 79.8, "recorded_at": timestamp("12:40" if party == "RIDER" else pickup)},
            {"lat": 6.91, "lng": 79.81, "recorded_at": timestamp(drop)}],
        "complaint": {"id": "complaint", "type": complaint},
        "zone_snapshot": {"zone_id": "z", "open_orders_count": 10, "late_orders_count": 8 if party == "EXTERNAL" else 0},
    })


def payload_for(party="RIDER", complaint="late"):
    case = case_for(party, complaint)
    with patch("backend.app.checks.timing.predict_minutes", return_value=None):
        return AggregatorInput(case=case, check_results=checks.run_all(case))


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.app.ml.fault_model import extract_features
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "fixture.joblib"
        rows, labels = [], []
        for party in ["MERCHANT", "RIDER", "EXTERNAL", "NEITHER"]:
            row = extract_features(payload_for(party))
            for _ in range(20):
                rows.append(row)
                labels.append(party)
        estimator = make_pipeline(SimpleImputer(strategy="constant", fill_value=0),
                                  RandomForestClassifier(n_estimators=31, max_depth=2, max_features=2, random_state=7))
        estimator.fit(pd.DataFrame(rows, columns=FEATURES), labels)
        cls.bundle = dict(pipeline=estimator, features=list(FEATURES), model_name="test_fixture_only", model_version="fixture-1")
        joblib.dump(cls.bundle, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        fault_model.load(self.path)

    def test_trained_predictions_and_actual_method_calls(self):
        estimator = fault_model.estimator
        confidences = []
        for party in ["MERCHANT", "RIDER", "EXTERNAL"]:
            with patch.object(estimator, "predict", wraps=estimator.predict) as predict, patch.object(estimator, "predict_proba", wraps=estimator.predict_proba) as proba:
                with self.assertLogs("backend.app.ml.fault_model", level="INFO") as logs:
                    verdict = run_aggregator(payload_for(party))
                print(logs.output[0])
                predict.assert_called_once()
                proba.assert_called_once()
                self.assertTrue(verdict.model_used)
                self.assertEqual(verdict.fault_prediction, party)
                self.assertAlmostEqual(sum(verdict.class_probabilities.values()), 1)
                self.assertEqual(verdict.confidence, max(verdict.class_probabilities.values()))
                self.assertEqual(verdict.fault_confidence, verdict.confidence)
                self.assertEqual(list(predict.call_args.args[0].columns), list(FEATURES))
                self.assertEqual(verdict.feature_names, list(verdict.features))
                confidences.append(verdict.confidence)
        self.assertGreater(len(set(confidences)), 1)

    def test_photo_constraint_keeps_inference(self):
        late = run_aggregator(payload_for())
        damaged = run_aggregator(payload_for(complaint="damaged"))
        self.assertTrue(damaged.model_used)
        self.assertEqual(damaged.outcome.value, "NEED_MORE_INFO")
        self.assertNotEqual(late.outcome.value, "NEED_MORE_INFO")
        self.assertEqual(damaged.confidence, late.confidence)

    def test_missing_and_failed_model_are_explicit(self):
        fault_model.load(self.path.with_name("missing.joblib"))
        verdict = run_aggregator(payload_for())
        self.assertFalse(verdict.model_used)
        self.assertIn("loading failed", verdict.fallback_reason)
        self.assertFalse(verdict.class_probabilities)
        fault_model.load(self.path)
        with patch.object(fault_model.estimator, "predict_proba", side_effect=RuntimeError("test failure")):
            verdict = run_aggregator(payload_for())
        self.assertFalse(verdict.model_used)
        self.assertIn("test failure", verdict.fallback_reason)
        self.assertIsNone(verdict.model_prediction)

    def test_bad_schema_and_probabilities_rejected(self):
        bad = dict(self.bundle, features=list(reversed(FEATURES)))
        path = self.path.with_name("bad.joblib")
        joblib.dump(bad, path)
        model = FaultModel()
        model.load(path)
        self.assertIsNone(model.estimator)
        self.assertIn("order", model.error)
        with patch.object(fault_model.estimator, "predict_proba", return_value=[[np.nan, 0, 0, 1]]):
            self.assertFalse(run_aggregator(payload_for()).model_used)

    def test_high_claim_history_risk_goes_to_admin_review(self):
        payload = payload_for()
        history = next(c for c in payload.check_results if c.check_name.value == "claim_history")
        history.flagged = True
        history.details["risk_score"] = 0.62
        verdict = run_aggregator(payload)
        self.assertEqual(verdict.outcome.value, "SUPPORT_TICKET")
        self.assertEqual(verdict.claim_assessment["risk_level"], "REVIEW")

    def test_low_claim_history_risk_auto_refunds_supported_late_claim(self):
        payload = payload_for()
        history = next(c for c in payload.check_results if c.check_name.value == "claim_history")
        history.flagged = False
        history.details["risk_score"] = 0.18
        verdict = run_aggregator(payload)
        self.assertEqual(verdict.outcome.value, "AUTO_REFUND")
        self.assertTrue(verdict.claim_assessment["auto_refund_eligible"])

    def test_check_confidences_do_not_control_model_confidence(self):
        payload = payload_for()
        first = run_aggregator(payload)
        for check in payload.check_results:
            check.confidence = 0.01
        second = run_aggregator(payload)
        self.assertTrue(second.model_used)
        self.assertEqual(first.confidence, second.confidence)
        self.assertEqual(first.class_probabilities, second.class_probabilities)

    def test_missing_evidence_explicitly_falls_back(self):
        payload = payload_for()
        payload.check_results = [c for c in payload.check_results if c.check_name != CheckName.timing]
        verdict = run_aggregator(payload)
        self.assertFalse(verdict.model_used)
        self.assertIn("Missing evidence checks", verdict.fallback_reason)

    def test_endpoint_infers_and_persisted_metadata_round_trips(self):
        sb = MagicMock()
        case = case_for()
        with patch.object(cases, "build_case", return_value=case), patch.object(cases, "get_supabase", return_value=sb), patch("backend.app.workflows.get_supabase", return_value=sb), patch("backend.app.workflows.rows", return_value=[]), patch("backend.app.checks.timing.predict_minutes", return_value=None), patch.object(fault_model.estimator, "predict", wraps=fault_model.estimator.predict) as predict:
            response = cases.create_case(CreateCaseRequest(order_id="order-1"))
        predict.assert_called_once()
        self.assertTrue(response.verdict.model_used)
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": case.case_id, "status": "resolved", "case_payload": case.model_dump(mode="json")}
        ]
        with patch.object(cases, "get_supabase", return_value=sb):
            fetched = cases.get_case(case.case_id)
        self.assertEqual(fetched.verdict, response.verdict)

    def test_constraint_failure_is_explicit_and_case_not_marked_aggregated(self):
        from fastapi import HTTPException
        from postgrest.exceptions import APIError
        sb = MagicMock()
        tables = {name: MagicMock() for name in ["complaints", "cases", "check_results", "verdicts", "refund_history", "support_tickets"]}
        sb.table.side_effect = lambda name: tables[name]
        tables["verdicts"].upsert.return_value.execute.side_effect = APIError({"code": "23514", "message": "violates verdicts_fault_party_check", "details": "", "hint": ""})
        with patch.object(cases, "build_case", return_value=case_for()), patch.object(cases, "get_supabase", return_value=sb), patch("backend.app.workflows.get_supabase", return_value=sb), patch("backend.app.workflows.rows", return_value=[]), patch("backend.app.checks.timing.predict_minutes", return_value=None):
            with self.assertRaises(HTTPException) as error:
                cases.create_case(CreateCaseRequest(order_id="order-1"))
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("could not be fully saved", error.exception.detail)
        self.assertEqual(tables["cases"].insert.call_args.args[0]["status"], "open")
        tables["cases"].update.assert_not_called()

    def test_startup_loads_once_and_status_reports_actual_state(self):
        with patch("backend.app.main.settings.fault_model_path", str(self.path)), patch("backend.app.ml.fault_model.joblib.load", wraps=joblib.load) as load:
            with TestClient(app) as client:
                self.assertTrue(client.get("/api/model/status").json()["fault_model_loaded"])
                for _ in range(2):
                    response = client.post("/aggregator/run", json=payload_for().model_dump(mode="json"))
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()["model_used"])
                self.assertEqual(load.call_count, 2)  # One load for each model at startup.
                self.assertEqual(sum(str(call.args[0]) == str(self.path) for call in load.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()

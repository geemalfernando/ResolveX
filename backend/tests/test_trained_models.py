"""Integration tests against the real locally trained dataset-derived artifacts.

Missing artifacts fail: run the documented training commands first.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ml.dataset_config import ETA_FEATURES, FAULT_FEATURES, MODEL_DIR, PROCESSED_DIR
from backend.app.ml.eta_model import eta_model
from backend.app.ml.fault_model import fault_model
from backend.app.ml.prepare_training_data import normalize_sources
from backend.app.routers import cases
from test_fault_inference import case_for


class TrainedModelTests(unittest.TestCase):
    def test_source_traceability_and_split(self):
        data = pd.read_csv(PROCESSED_DIR / "fault_training_data.csv")
        self.assertEqual(set(data.source_dataset), {"zomato", "kaggle_synthetic"})
        self.assertEqual(set(data.fault_party), {"MERCHANT", "RIDER", "EXTERNAL", "NEITHER"})
        train, test = data[data.split == "train"], data[data.split == "test"]
        self.assertFalse(set(zip(train.source_dataset, train.source_row_id)) & set(zip(test.source_dataset, test.source_row_id)))
        operational = pd.read_csv(PROCESSED_DIR / "combined_delivery_data.csv")
        self.assertTrue(set(zip(data.source_dataset, data.source_row_id)) <= set(zip(operational.source_dataset, operational.source_row_id)))
        self.assertEqual(data.groupby(["source_dataset", "source_row_id"]).scenario.nunique().min(), 4)
        self.assertNotIn("claim_risk", FAULT_FEATURES)
        self.assertNotIn("claims_last_90_days", FAULT_FEATURES)

    def test_saved_eta_beats_baseline_on_held_out_data(self):
        metadata = json.loads((MODEL_DIR / "eta_model_metadata.json").read_text())
        self.assertLess(metadata["test_metrics"]["mae_min"], metadata["baseline_test_mae_min"])
        estimator = joblib.load(MODEL_DIR / "eta_model.joblib")["pipeline"]
        self.assertEqual(list(estimator.feature_names_in_), ETA_FEATURES)

    def test_original_moderate_rider_goes_to_support_without_changing_confidence(self):
        from backend.app import checks
        from backend.app.models import AggregatorInput
        with TestClient(app) as client:
            case = case_for("RIDER")
            case.zone_snapshot.average_delay_minutes = 0
            payload = AggregatorInput(case=case, check_results=checks.run_all(case))
            response = client.post("/aggregator/run", json=payload.model_dump(mode="json"))
        self.assertEqual(response.status_code, 200)
        verdict = response.json()
        self.assertTrue(verdict["model_used"])
        self.assertEqual(verdict["model_prediction"], "RIDER")
        self.assertEqual(verdict["outcome"], "SUPPORT_TICKET")
        self.assertGreaterEqual(verdict["confidence"], 0.55)
        self.assertLess(verdict["confidence"], 0.85)
        self.assertEqual(verdict["confidence"], max(verdict["class_probabilities"].values()))

    def test_actual_cases_http_pipeline_all_four_classes(self):
        results = []
        with TestClient(app) as client:
            status = client.get("/api/model/status").json()
            self.assertTrue(status["eta_model_loaded"])
            self.assertTrue(status["fault_model_loaded"])
            self.assertIn("not genuine historical", status["label_provenance"])
            self.assertEqual(status["feature_names"], FAULT_FEATURES)
            for party in ["MERCHANT", "RIDER", "EXTERNAL", "NEITHER"]:
                case = case_for(party)
                case.zone_snapshot.average_delay_minutes = 25 if party == "EXTERNAL" else 0
                sb = MagicMock()
                with patch.object(cases, "build_case", return_value=case), patch.object(cases, "get_supabase", return_value=sb), patch.object(fault_model.estimator, "predict", wraps=fault_model.estimator.predict) as predict, patch.object(fault_model.estimator, "predict_proba", wraps=fault_model.estimator.predict_proba) as proba, patch.object(eta_model.estimator, "predict", wraps=eta_model.estimator.predict) as eta_predict:
                    response = client.post("/cases", json={"order_id": "order-1", "complaint_type": "late"})
                self.assertEqual(response.status_code, 200, response.text)
                verdict = response.json()["verdict"]
                predict.assert_called_once()
                proba.assert_called_once()
                eta_predict.assert_called_once()
                self.assertTrue(verdict["model_used"])
                self.assertEqual(verdict["model_prediction"], party)
                self.assertAlmostEqual(sum(verdict["class_probabilities"].values()), 1)
                self.assertEqual(verdict["confidence"], max(verdict["class_probabilities"].values()))
                self.assertEqual(verdict["feature_names"], FAULT_FEATURES)
                results.append({"case": party, "verdict": verdict})
            self.assertEqual(len(set(r["verdict"]["confidence"] for r in results)), 4)
        # Auditable real artifact predictions; only the external database is mocked.
        output = PROCESSED_DIR / "api_model_verification.json"
        output.write_text(json.dumps(results, indent=2))
        print(f"Actual model/API verification saved to {output}")

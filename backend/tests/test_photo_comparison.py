import unittest
from unittest.mock import patch

from backend.app.aggregator.aggregator import _local_decision_engine
from backend.app.checks import photo as photo_check
from backend.app.models import AggregatorInput, CheckName, DeliveryEvidence
from backend.tests.test_fault_inference import case_for, payload_for


class PhotoComparisonTests(unittest.TestCase):
    def test_missing_claim_photo_stays_need_more_info(self):
        payload = payload_for(complaint="damaged")
        photo = next(c for c in payload.check_results if c.check_name == CheckName.photo)
        self.assertEqual(photo.details.get("source"), "missing_photo")
        self.assertIsNone(photo.details.get("comparison_party"))

    def test_comparison_is_an_evidence_signal_not_the_verdict(self):
        case = case_for("RIDER", "damaged")
        case.complaint.photo_url = "order-1/claim.jpg"
        case.evidence = DeliveryEvidence(
            packing_path="order-1/packing.jpg",
            handover_path="order-1/handover.jpg",
            claim_path="order-1/claim.jpg",
        )
        comparison = {
            "fault_party": "MERCHANT",
            "confidence": 0.91,
            "reasons": ["Packing already shows crushed packaging."],
            "match": True,
            "damage_detected": True,
            "detected_items": ["Chicken rice"],
            "complaint_supported": True,
            "source": "gemini",
        }
        jpeg = (b"fake-bytes", "image/jpeg")
        with patch.object(photo_check, "_evidence_images", return_value={"packing": jpeg, "handover": jpeg, "claim": jpeg}):
            with patch.object(photo_check, "_compare_three", return_value=comparison):
                with patch("backend.app.evidence.save_comparison"):
                    result = photo_check.run(case)
        self.assertEqual(result.details["comparison_party"], "MERCHANT")
        self.assertTrue(result.flagged)
        payload = AggregatorInput(case=case, check_results=[result])
        decision = _local_decision_engine(payload)
        self.assertEqual(decision["fault_party"], "merchant")
        self.assertIn("photo", decision["reasons"][0]["check"])

    def test_neither_comparison_does_not_flag_the_photo_check(self):
        case = case_for("NEITHER", "damaged")
        case.complaint.photo_url = "order-1/claim.jpg"
        jpeg = (b"fake-bytes", "image/jpeg")
        with patch.object(photo_check, "_evidence_images", return_value={"packing": jpeg, "handover": jpeg, "claim": jpeg}):
            with patch.object(photo_check, "_compare_three", return_value={
                "fault_party": "NEITHER",
                "confidence": 0.8,
                "reasons": ["All three photos match the packed order."],
                "match": True,
                "damage_detected": False,
                "complaint_supported": False,
                "source": "gemini",
            }):
                with patch("backend.app.evidence.save_comparison"):
                    result = photo_check.run(case)
        self.assertFalse(result.flagged)
        self.assertEqual(result.details["comparison_party"], "NEITHER")
        self.assertIs(result.details["complaint_supported"], False)

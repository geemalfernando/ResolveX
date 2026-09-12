import unittest
from unittest.mock import MagicMock, patch
from backend.tests.test_fault_inference import case_for
from backend.app import workflows as wf
from backend.app.models import CheckResult, Verdict, OrderItem

class RefundAutomationTests(unittest.TestCase):
    def test_existing_order_refund_reused_across_cases(self):
        case = case_for();case.order.items = [OrderItem(name='Meal', qty=2, price=800)]
        with patch.object(wf, 'rows', return_value=[dict(id='12345678-existing',amount=1600,outcome='approved',created_at='2026-01-01')]), patch.object(wf,'get_supabase') as db:
            refund = wf.refund(case)
        self.assertEqual(refund['amount'],1600)
        db.assert_not_called()

    def test_low_risk_refund_and_high_risk_review(self):
        cases = [(0.0, False, "AUTO_REFUND"), (0.39, False, "AUTO_REFUND"), (0.41, False, "SUPPORT_TICKET"), (0.9, True, "SUPPORT_TICKET")]
        for risk, flagged, outcome in cases:
            with self.subTest(risk=risk, flagged=flagged):
                case=case_for()
                check=CheckResult(check_name='claim_history',flagged=flagged,confidence=.9,summary='History screened',details=dict(risk_score=risk,source='rules'))
                verdict=Verdict(claim_valid=True,fault_party='rider',confidence=.99,outcome='AUTO_REFUND',reasons=[])
                with patch.object(wf,'get_supabase',return_value=MagicMock()), patch.object(wf,'save_case'), patch.object(wf,'close_tickets'), patch.object(wf,'ticket') as ticket, patch.object(wf,'refund') as refund:
                    result=wf.persist_analysis(case,[check],verdict)
                self.assertEqual(result.verdict.outcome.value, outcome)
                self.assertEqual(refund.call_count, 1 if outcome == "AUTO_REFUND" else 0)
                self.assertEqual(ticket.call_count, 0 if outcome == "AUTO_REFUND" else 1)
                self.assertEqual(case.workflow['fraud_screening']['status'], 'low_risk' if outcome == "AUTO_REFUND" else 'review_required')

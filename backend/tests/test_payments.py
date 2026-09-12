import unittest
from unittest.mock import MagicMock, patch

from backend.app import workflows as wf
from backend.app.models import OrderItem, PaymentSnapshot
from backend.app.payments import PaymentError, account_label, charge, charge_demo, pending, refund_to_source
from backend.tests.test_fault_inference import case_for


class PaymentGatewayTests(unittest.TestCase):
    def test_charge_keeps_last4_not_pan(self):
        payment = charge("Demo Customer", "4242 4242 4242 4242", "12/28", "123", 2500)
        self.assertEqual(payment["gateway"], "ResolveX Pay")
        self.assertEqual(payment["last4"], "4242")
        self.assertEqual(payment["brand"], "Visa")
        self.assertEqual(payment["account"], "Visa ••4242")
        self.assertEqual(payment["amount"], 2500)
        self.assertNotIn("number", payment)

    def test_declined_demo_card(self):
        with self.assertRaises(PaymentError):
            charge("Demo Customer", "4000000000000002", "12/28", "123", 1000)

    def test_refund_returns_to_charged_account(self):
        payment = charge("Demo Customer", "5555555555554444", "12/28", "123", 1600)
        payout = refund_to_source(payment, 1600)
        self.assertEqual(payout["destination"], "Mastercard ••4444")
        self.assertEqual(payout["status"], "completed")
        self.assertEqual(account_label(None), "ResolveX Pay wallet")

    def test_pending_then_demo_charge(self):
        stub = pending(1250)
        self.assertEqual(stub["status"], "pending")
        payment = charge_demo(1250)
        self.assertEqual(payment["status"], "captured")
        self.assertEqual(payment["last4"], "4242")


class RefundToCardTests(unittest.TestCase):
    def test_refund_uses_checkout_card(self):
        case = case_for()
        case.order.items = [OrderItem(name="Meal", qty=2, price=800)]
        case.payment = PaymentSnapshot(account="Visa ••4242", brand="Visa", last4="4242", payment_id="pay-1")
        with patch.object(wf, "rows", return_value=[]), patch.object(wf, "get_supabase") as db:
            db.return_value.table.return_value.upsert.return_value.execute.return_value = MagicMock()
            refund = wf.refund(case)
        self.assertEqual(refund["destination"], "Visa ••4242")
        self.assertEqual(refund["gateway"], "ResolveX Pay")
        self.assertEqual(refund["amount"], 1600)

"""Regression checks for combining auth and admin claim-risk branches."""
import unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.auth import current_user, AuthPrincipal

class BranchIntegrationTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_operational_endpoints_require_login(self):
        client = TestClient(app)
        for path in ['/workflow/ops', '/workflow/ops/positions', '/workflow/admin', '/demo/state']:
            self.assertEqual(client.get(path).status_code, 401, path)

    def test_customer_cannot_access_admin_or_ops(self):
        app.dependency_overrides[current_user] = lambda: AuthPrincipal(user_id='test', email='test@example.invalid', role='customer')
        client = TestClient(app)
        for path in ['/workflow/ops', '/workflow/ops/positions', '/workflow/admin']:
            self.assertEqual(client.get(path).status_code, 403, path)

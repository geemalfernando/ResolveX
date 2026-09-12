"""Regression for PostgreSQL timestamps with variable fractional precision."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.case_builder import _zone_snapshot


class ZoneTimestampTests(unittest.TestCase):
    def test_postgres_fractional_timestamps_build_zone(self):
        rows = [dict(placed_at=f"2026-01-01T00:00:00{fraction}{offset}",
                     promised_delivery_minutes=30, is_late_flagged=True)
                for fraction in ("", ".1", ".123", ".61243", ".123456")
                for offset in ("+00:00", "Z")]
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=rows)
        with patch('backend.app.case_builder.get_supabase', return_value=sb):
            zone = _zone_snapshot('test-zone')
        self.assertEqual(zone.open_orders_count, 10)
        self.assertEqual(zone.late_orders_count, 10)
        self.assertGreater(zone.average_delay_minutes, 0)

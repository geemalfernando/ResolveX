import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.routers import rider_join as rj


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self.action = "select"
        self.body = None

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        self.filters.append((k, v))
        return self

    def limit(self, n):
        return self

    def insert(self, body):
        self.action = "insert"
        self.body = body
        return self

    def delete(self):
        self.action = "delete"
        return self

    def execute(self):
        if self.action == "insert":
            if "last_location_at" in (self.body or {}) or "lat" in (self.body or {}):
                raise RuntimeError("Could not find the 'last_location_at' column of 'riders'")
            if self.table == "user_profiles" and "rider_id" in (self.body or {}):
                raise RuntimeError('column user_profiles.rider_id does not exist')
            if self.table == "user_profiles" and self.body.get("role") == "rider":
                raise RuntimeError('violates check constraint "user_profiles_role_check"')
            self.db[self.table].append(dict(self.body))
            return SimpleNamespace(data=[self.body])
        rows = self.db[self.table]
        for key, value in self.filters:
            rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=rows)


class FakeSB:
    def __init__(self):
        self.tables = {"riders": [], "user_profiles": [], "merchants": [{"zone_id": "ZONE_A", "lat": 6.91, "lng": 79.85}]}
        self.auth = SimpleNamespace(
            admin=SimpleNamespace(
                create_user=lambda payload: SimpleNamespace(user=SimpleNamespace(id="user-1")),
                delete_user=lambda uid: None,
            )
        )

    def table(self, name):
        return FakeQuery(self.tables, name)


class RiderJoinTests(unittest.TestCase):
    def test_join_works_without_location_migration(self):
        sb = FakeSB()
        with patch.object(rj, "get_supabase", return_value=sb), patch.object(rj, "rider_geo_available", return_value=False):
            result = rj.join_as_rider(
                rj.RiderJoinRequest(
                    name="Kasun Perera",
                    email="kasun@example.com",
                    password="ResolveX@Rider26",
                    phone="0771234567",
                    zone_id="ZONE_A",
                    lat=6.91,
                    lng=79.85,
                )
            )
        self.assertTrue(result["created"])
        self.assertEqual(len(sb.tables["riders"]), 1)
        self.assertNotIn("last_location_at", sb.tables["riders"][0])
        self.assertEqual(sb.tables["user_profiles"], [])

"""Runs all five checks against a Case and returns their CheckResult list."""

from __future__ import annotations

from ..models import Case, CheckResult
from . import claim_history, photo, rider_route, timing, zone


def run_all(case: Case) -> list[CheckResult]:
    return [
        timing.run(case),
        rider_route.run(case),
        zone.run(case),
        claim_history.run(case),
        photo.run(case),
    ]

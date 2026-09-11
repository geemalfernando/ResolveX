"""Debug/dev endpoints to run the 5 checks against an order without persisting a case.
Handy for testing individual checks while wiring up the frontend or the Gemini key.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import checks as check_registry
from ..case_builder import build_case
from ..models import CaseTrigger, CheckResult

router = APIRouter(prefix="/checks", tags=["checks"])


@router.get("/{order_id}", response_model=list[CheckResult])
def run_checks_for_order(order_id: str) -> list[CheckResult]:
    try:
        case = build_case(order_id=order_id, trigger=CaseTrigger.live_feed_late)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return check_registry.run_all(case)

"""Debug/dev endpoint to run the Fairness Aggregator directly against a case + check results,
without going through the full /cases pipeline. Useful for prompt-tuning the Gemini call.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..aggregator.aggregator import run_aggregator
from ..models import AggregatorInput, Verdict

router = APIRouter(prefix="/aggregator", tags=["aggregator"])


@router.post("/run", response_model=Verdict)
def run(payload: AggregatorInput) -> Verdict:
    return run_aggregator(payload)

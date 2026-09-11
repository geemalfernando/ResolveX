"""Opt-in real HTTP/DB verification; creates clearly named isolated demo records.

Run against the local backend with the configured Supabase project. No mocks.
Leaves case/order IDs in the JSON report for inspection; does not delete user data.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.db import get_supabase
from backend.app.ml.dataset_config import PROCESSED_DIR


def main():
    sb = get_supabase()
    run_id = uuid.uuid4().hex[:8]
    report = {"run_id": run_id, "test_records_retained": True, "cases": []}
    output = PROCESSED_DIR / "live_integration_verification.json"
    def save():
        output.write_text(json.dumps(report, indent=2))
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60) as client:
        status = client.get("/api/model/status")
        status.raise_for_status()
        report["model_status"] = status.json()
        assert report["model_status"]["eta_model"]["loaded"]
        assert report["model_status"]["fault_model"]["loaded"]
        assert not report["model_status"]["eta_model"]["fallback_reason"]
        assert not report["model_status"]["fault_model"]["fallback_reason"]
        for party in ["MERCHANT", "RIDER", "EXTERNAL", "NEITHER"]:
            merchant, rider, customer, order = [str(uuid.uuid4()) for _ in range(4)]
            zone = f"ML_VERIFY_{run_id}_{party}"
            sb.table("merchants").insert(dict(id=merchant, name=f"ML verification {run_id} {party}", zone_id=zone, address="Demo test only", lat=6.9, lng=79.8, avg_prep_minutes=10)).execute()
            sb.table("riders").insert(dict(id=rider, name=f"ML verification {run_id}", phone="0000000000", vehicle="bike", zone_id=zone)).execute()
            sb.table("customers").insert(dict(id=customer, name=f"ML verification {run_id}", email=f"{customer}@example.invalid", phone="0000000000", address="Demo test only", lat=6.91, lng=79.81, zone_id=zone)).execute()
            # Fixed completed timestamps make the four demonstration cases reproducible.
            placed = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
            ready, pickup, drop = (50, 52, 70) if party == "MERCHANT" else (12, 15, 80 if party != "NEITHER" else 30)
            stamp = lambda minutes: (placed + timedelta(minutes=minutes)).isoformat()
            base = dict(merchant_id=merchant, rider_id=rider, customer_id=customer, zone_id=zone,
                        items=[dict(name="Demo meal", qty=1, price=10)], promised_prep_minutes=10, promised_delivery_minutes=30)
            sb.table("orders").insert(dict(base, id=order, status="dropped_off", placed_at=stamp(0), prep_started_at=stamp(0), ready_at=stamp(ready), picked_up_at=stamp(pickup), dropped_off_at=stamp(drop), is_late_flagged=party != "NEITHER")).execute()
            trail = [dict(order_id=order, rider_id=rider, lat=6.9, lng=79.8, recorded_at=stamp(pickup)),
                     dict(order_id=order, rider_id=rider, lat=6.9, lng=79.8, recorded_at=stamp(40 if party == "RIDER" else pickup)),
                     dict(order_id=order, rider_id=rider, lat=6.91, lng=79.81, recorded_at=stamp(drop))]
            if party == "RIDER":
                trail.insert(2, dict(order_id=order, rider_id=rider, lat=6.91, lng=79.79, recorded_at=stamp(55)))
            sb.table("rider_gps_points").insert(trail).execute()
            now = datetime.now(timezone.utc)
            background = [dict(base, id=str(uuid.uuid4()), status="preparing", placed_at=(now-timedelta(minutes=61.25 if party == "EXTERNAL" and i < 8 else 5)).isoformat(), is_late_flagged=party == "EXTERNAL" and i < 8) for i in range(10)]
            sb.table("orders").insert(background).execute()
            result = dict(expected=party, order_id=order, zone_id=zone, background_order_ids=[r["id"] for r in background])
            report["cases"].append(result)
            save()
            response = client.post("/cases", json=dict(order_id=order, complaint_type="late", description=f"Isolated ML integration verification {run_id}: {party}"))
            result["http_status"] = response.status_code
            if response.status_code != 200:
                result["error"] = response.text
                case_rows = sb.table("cases").select("id,case_payload").eq("order_id", order).execute().data
                if case_rows:
                    case_row = case_rows[0]
                    result["case_id"] = case_row["id"]
                    check_rows = sb.table("check_results").select("result").eq("case_id", case_row["id"]).execute().data
                    analysis = client.post("/aggregator/run", json={"case": case_row["case_payload"], "check_results": [r["result"] for r in check_rows]})
                    if analysis.status_code == 200:
                        result["unsaved_verdict"] = analysis.json()
                save()
                print(party, "FAILED", response.status_code, flush=True)
                continue
            body = response.json()
            result["case_id"] = body["case_id"]
            result["response"] = body
            verdict = body["verdict"]
            fetched = client.get("/cases/" + body["case_id"])
            fetched.raise_for_status()
            persisted = sb.table("verdicts").select("fault_party,confidence,raw_llm_response").eq("case_id", body["case_id"]).single().execute().data
            result["checks"] = {
                "model_used": verdict["model_used"], "prediction_matches": verdict["fault_prediction"] == party,
                "probabilities_sum_one": abs(sum(verdict["class_probabilities"].values()) - 1) < 1e-9,
                "confidence_is_max_probability": verdict["confidence"] == max(verdict["class_probabilities"].values()),
                "get_verdict_matches": fetched.json()["verdict"] == verdict,
                "db_verdict_matches": persisted["raw_llm_response"] == verdict,
                "db_fault_matches": persisted["fault_party"].upper() == party,
                "separate_eta_fault_resolution": all(k in body for k in ["eta", "fault", "resolution"]),
            }
            if verdict["outcome"] == "SUPPORT_TICKET":
                result["checks"]["support_ticket_persisted"] = bool(sb.table("support_tickets").select("id").eq("case_id", body["case_id"]).execute().data)
            save()
            print(party, verdict["class_probabilities"], verdict["outcome"], result["checks"], flush=True)
        inferences = [r.get("response", {}).get("verdict") or r.get("unsaved_verdict") for r in report["cases"]]
        probabilities = [v["confidence"] for v in inferences if v]
        report["confidence_varies"] = len(set(probabilities)) == 4
        report["passed"] = all("checks" in r and all(r["checks"].values()) for r in report["cases"]) and report["confidence_varies"]
        save()
        print("Report:", output, "passed:", report["passed"])
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

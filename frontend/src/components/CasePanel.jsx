import RiderRouteCheck from "./RiderRouteCheck";
import OutcomeBadge from "./OutcomeBadge.jsx";
import { actionLabel, faultLabel, publicFault, resolution } from "../lib/api";

export default function CasePanel({ record, technical = false }) {
  const c = record.case;
  const v = record.verdict;
  const w = c?.workflow ?? {};
  if (!c) return null;
  const results = record.check_results ?? w.checks ?? [];
  const timing = results.find((r) => r.check_name === "timing")?.details ?? {};
  const routeCheck = results.find((r) => r.check_name === "rider_route");
  const zone = results.find((r) => r.check_name === "zone")?.details ?? {};
  const photo = results.find((r) => r.check_name === "photo")?.details ?? {};
  const history = results.find((r) => r.check_name === "claim_history")?.details ?? {};
  const outcome = resolution(record);

  return (
    <section className="space-y-4" data-testid="case-panel">
      <div className="overflow-hidden rounded-2xl bg-slate-900 text-white">
        <div className="px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-teal-200">Decision</p>
              <h2 className="mt-1 text-2xl font-bold">{actionLabel(outcome)}</h2>
              <p className="mt-1 text-sm text-slate-300">{faultLabel(publicFault(record))}</p>
            </div>
            <OutcomeBadge outcome={outcome} large />
          </div>
          {v && <p className="mt-3 text-sm text-slate-300">Confidence {(v.confidence * 100).toFixed(0)}%</p>}
          {w.refund && (
            <div className="mt-3 rounded-xl bg-emerald-400/15 px-3 py-2 text-emerald-100">
              <p className="font-semibold">LKR {w.refund.amount.toLocaleString()} · {w.refund.status}</p>
              <p className="text-xs">{w.refund.reference} · Demo refund</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <div>
          <h3 className="font-semibold">Case {record.case_id?.slice(0, 8).toUpperCase()}</h3>
          <p className="text-xs text-slate-500">Order {c.order.id.slice(0, 8)}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize">{record.status}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl bg-slate-50 p-4 text-sm">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Complaint</p>
          <p className="mt-1 font-semibold capitalize">{c.complaint?.type?.replaceAll("_", " ") ?? "Proactive incident"}</p>
          <p className="mt-1 text-slate-600">{c.complaint?.description || "No customer complaint"}</p>
        </div>
        <div className="rounded-2xl bg-slate-50 p-4 text-sm">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Evidence</p>
          <p className="mt-1">Timing {timing.delivery_minutes ?? "—"} / {timing.delivery_promised_minutes ?? "—"} min</p>
          <p>Zone delay {((zone.late_ratio ?? 0) * 100).toFixed(0)}%</p>
          <p>Photo {c.complaint?.photo_url ? (photo.complaint_supported === true ? "supports complaint" : "on file") : "not attached"}</p>
          {technical && <p>Claim history {history.claims_last_90_days ?? 0} prior · {v?.claim_assessment?.risk_level ?? "n/a"}</p>}
        </div>
      </div>

      <RiderRouteCheck check={routeCheck} />
      {w.partner && <p className="text-sm"><b>Partner:</b> {w.partner.status} — {w.partner.reason}</p>}

      <details className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
        <div className="mt-3 space-y-2">
          {Object.entries(v?.class_probabilities ?? {}).sort((a, b) => b[1] - a[1]).map(([label, prob]) => (
            <div key={label}>
              <div className="flex justify-between text-xs"><span>{label}</span><span>{(prob * 100).toFixed(0)}%</span></div>
              <div className="h-1.5 rounded bg-slate-100"><div className="h-1.5 rounded bg-teal-600" style={{ width: `${prob * 100}%` }} /></div>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

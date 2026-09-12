import RiderRouteCheck from "./RiderRouteCheck";
import OutcomeBadge from "./OutcomeBadge.jsx";
import { actionLabel, faultLabel, publicFault, resolution } from "../lib/api";

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function CasePanel({ record, technical = false }) {
  const c = record.case;
  const v = record.verdict;
  const w = c?.workflow ?? {};
  if (!c) return null;

  const results = record.check_results ?? w.checks ?? [];
  const timingCheck = results.find((r) => r.check_name === "timing");
  const timing = timingCheck?.details ?? {};
  const routeCheck = results.find((r) => r.check_name === "rider_route");
  const zoneCheck = results.find((r) => r.check_name === "zone");
  const zone = zoneCheck?.details ?? {};
  const photoCheck = results.find((r) => r.check_name === "photo");
  const photo = photoCheck?.details ?? {};
  const historyCheck = results.find((r) => r.check_name === "claim_history");
  const history = historyCheck?.details ?? {};
  const outcome = resolution(record);
  const externalCause = v?.model_prediction === "EXTERNAL" || v?.cause_category === "EXTERNAL";
  const timeline = w.timeline ?? [];
  const reasons = v?.reasons ?? [];

  return (
    <section className="space-y-4" data-testid="case-panel">
      <div className="overflow-hidden rounded-2xl bg-slate-900 text-white">
        <div className="px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-teal-200">Decision</p>
              <h2 className="mt-1 text-2xl font-bold">{actionLabel(outcome)}</h2>
              <p className="mt-1 text-sm text-slate-300">
                {faultLabel(publicFault(record))}{externalCause ? " · zone-wide / external conditions" : ""}
              </p>
            </div>
            <OutcomeBadge outcome={outcome} large />
          </div>
          {v && (
            <p className="mt-3 text-sm text-slate-300">
              Assessment confidence {(v.confidence * 100).toFixed(0)}%
            </p>
          )}
          {w.refund && (
            <div className="mt-3 rounded-xl bg-emerald-400/15 px-3 py-2 text-emerald-100">
              <p className="font-semibold">LKR {Number(w.refund.amount).toLocaleString()} · {w.refund.status}</p>
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
          <p className="mt-1 text-slate-600">{c.complaint?.description || "Incident detected before a customer complaint."}</p>
          {c.complaint?.photo_url && (
            <a className="mt-2 inline-block text-xs font-medium text-teal-800 underline" href={c.complaint.photo_url} target="_blank" rel="noreferrer">
              View evidence photo
            </a>
          )}
        </div>
        <div className="rounded-2xl bg-slate-50 p-4 text-sm">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Evidence snapshot</p>
          <p className="mt-1">Timing {timing.delivery_minutes ?? "—"} / {timing.delivery_promised_minutes ?? "—"} min</p>
          <p>Zone late {Math.round((zone.late_ratio ?? 0) * 100)}%</p>
          <p>Photo {c.complaint?.photo_url ? (photo.complaint_supported === true ? "supports complaint" : "reviewed") : "not attached"}</p>
          {externalCause && <p className="mt-1 font-medium text-amber-800">Neither party blamed: shared zone disruption detected.</p>}
          {technical && <p>Claim history {history.claims_last_90_days ?? 0} prior · risk {Math.round((history.risk_score ?? history.risk_probability ?? 0) * 100)}%</p>}
        </div>
      </div>

      {reasons.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold">Why this decision</h3>
          <ul className="mt-2 space-y-2 text-sm text-slate-600">
            {reasons.map((reason, index) => (
              <li key={`${reason.check ?? "reason"}-${index}`} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-600" />
                <span><b className="font-medium text-slate-800">{reason.check?.replaceAll("_", " ") ?? "Evidence"}:</b> {reason.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <RiderRouteCheck check={routeCheck} />

      {w.zone_incident && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">
          <h3 className="font-semibold text-amber-900">Zone incident {w.zone_incident.id}</h3>
          <p className="mt-1 text-amber-900/80">
            {w.zone_incident.late_orders ?? 0} late of {w.zone_incident.active_orders ?? 0} active orders · {w.zone_incident.customers_notified ?? 0} customers notified
          </p>
        </div>
      )}

      {w.partner && <p className="text-sm"><b>Partner:</b> {w.partner.status}{w.partner.reason ? ` — ${w.partner.reason}` : ""}</p>}

      {timeline.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold">Case timeline</h3>
          <ol className="mt-3 space-y-2">
            {timeline.slice().reverse().map((item, index) => (
              <li key={`${item.at}-${index}`} className="flex gap-3 text-xs text-slate-600">
                <span className="w-14 shrink-0 font-mono text-slate-400">{formatTime(item.at)}</span>
                <span>{item.label}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {technical && (
        <details className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium">Technical model details</summary>
          <div className="mt-3 space-y-3">
            <div className="grid gap-2 text-xs sm:grid-cols-2">
              <p><b>Model prediction:</b> {v?.model_prediction ?? "—"}</p>
              <p><b>Model used:</b> {v?.model_used === false ? "No" : "Yes"}</p>
              <p><b>Cause category:</b> {v?.cause_category ?? "—"}</p>
              <p><b>Resolution:</b> {outcome ?? "—"}</p>
            </div>
            {Object.entries(v?.class_probabilities ?? {}).sort((a, b) => b[1] - a[1]).map(([label, prob]) => (
              <div key={label}>
                <div className="flex justify-between text-xs"><span>{label}</span><span>{(prob * 100).toFixed(1)}%</span></div>
                <div className="h-1.5 rounded bg-slate-100"><div className="h-1.5 rounded bg-teal-600" style={{ width: `${prob * 100}%` }} /></div>
              </div>
            ))}
            <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
              <p><b>Timing:</b> {timingCheck?.summary ?? "No timing signal"}</p>
              <p><b>Zone:</b> {zoneCheck?.summary ?? "No zone signal"}</p>
              <p><b>Photo:</b> {photoCheck?.summary ?? "No photo signal"}</p>
              <p><b>Claim history:</b> {historyCheck?.summary ?? "No claim-history signal"}</p>
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

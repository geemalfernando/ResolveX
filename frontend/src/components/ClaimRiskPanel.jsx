/**
 * CLAIM HISTORY · AI panel for Support / Ops.
 * Reads check_results rows (or a single check_history CheckResult) and surfaces
 * risk_score, anomaly, and risk_flags — never shown on the customer app.
 */

function pct(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return 0;
  return Math.round(Math.min(Math.max(n, 0), 1) * 100);
}

function riskTone(score, flagged) {
  if (!flagged && score < 0.4) return "ok";
  if (score >= 0.75 || flagged) return "high";
  if (score >= 0.45) return "mid";
  return "ok";
}

export default function ClaimRiskPanel({ check, compact = false }) {
  if (!check) {
    return (
      <div className="rounded-md border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
        No claim-history signal on this case yet.
      </div>
    );
  }

  const details = check.result?.details ?? check.details ?? {};
  const flagged = Boolean(check.flagged ?? check.result?.flagged);
  const riskScore = details.risk_score ?? details.risk_probability ?? 0;
  const flags = details.risk_flags ?? [];
  const anomaly = Boolean(details.anomaly);
  const tone = riskTone(riskScore, flagged);
  const bar =
    tone === "high" ? "bg-rose-500" : tone === "mid" ? "bg-amber-500" : "bg-emerald-500";
  const badge =
    tone === "high"
      ? "bg-rose-100 text-rose-800"
      : tone === "mid"
        ? "bg-amber-100 text-amber-800"
        : "bg-emerald-100 text-emerald-800";

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Claim history · AI
        </div>
        <span className={`text-[11px] rounded-full px-2 py-0.5 font-medium ${badge}`}>
          {flagged || anomaly ? "anomaly / fraud risk" : "normal pattern"}
        </span>
      </div>

      <div className="mt-2 flex items-end justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold tabular-nums text-slate-900">{pct(riskScore)}</div>
          <div className="text-[11px] text-slate-500">risk score</div>
        </div>
        <div className="flex-1">
          <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
            <div className={`h-full ${bar}`} style={{ width: `${pct(riskScore)}%` }} />
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {details.claims_last_90_days ?? 0} claims / 90d · approved{" "}
            {Math.round((details.approved_ratio ?? 0) * 100)}%
            {anomaly ? " · IsolationForest anomaly" : ""}
          </div>
        </div>
      </div>

      {!compact && (
        <>
          {flags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {flags.map((f) => (
                <span
                  key={f}
                  className="rounded bg-white border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-700"
                >
                  {f.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          )}
          {check.result?.summary || check.summary ? (
            <p className="mt-2 text-xs text-slate-600">{check.result?.summary || check.summary}</p>
          ) : null}
        </>
      )}
    </div>
  );
}

export function pickClaimHistoryCheck(rows) {
  if (!Array.isArray(rows)) return null;
  return (
    rows.find((r) => (r.check_name || r.result?.check_name) === "claim_history") ?? null
  );
}

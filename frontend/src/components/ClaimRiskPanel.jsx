function pct(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return 0;
  return Math.round(Math.min(Math.max(n, 0), 1) * 100);
}

export const AUTO_REFUND_RISK_MAX = 0.4;

function riskTone(score, flagged) {
  if (score >= 0.75 || flagged) return "high";
  if (score >= AUTO_REFUND_RISK_MAX) return "mid";
  return "ok";
}

export default function ClaimRiskPanel({ check, compact = false }) {
  if (!check) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">
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
  const bar = tone === "high" ? "bg-rose-500" : tone === "mid" ? "bg-amber-500" : "bg-emerald-500";
  const badge =
    tone === "high"
      ? "bg-rose-100 text-rose-800"
      : tone === "mid"
        ? "bg-amber-100 text-amber-800"
        : "bg-emerald-100 text-emerald-800";

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Claim history · AI</div>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge}`}>
          {flagged || anomaly || riskScore >= AUTO_REFUND_RISK_MAX ? "Unusual pattern" : "Legitimate pattern"}
        </span>
      </div>
      <div className="mt-3 flex items-end justify-between gap-4">
        <div>
          <div className="text-4xl font-bold tabular-nums tracking-tight">{pct(riskScore)}%</div>
          <div className="text-xs text-slate-500">risk score</div>
        </div>
        <div className="flex-1">
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full ${bar}`} style={{ width: `${pct(riskScore)}%` }} />
          </div>
          <div className="relative mt-1 h-3 text-[10px] text-slate-400">
            <span className="absolute" style={{ left: `${AUTO_REFUND_RISK_MAX * 100}%`, transform: "translateX(-50%)" }}>
              40% auto
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {details.claims_last_90_days ?? 0} claims / 90d · approved {Math.round((details.approved_ratio ?? 0) * 100)}%
            {riskScore >= AUTO_REFUND_RISK_MAX || details.auto_refund_eligible === false
              ? " · hold refund"
              : " · instant refund"}
          </div>
        </div>
      </div>
      {!compact && flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {flags.map((f) => (
            <span key={f} className="rounded-full bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200">
              {f.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function pickClaimHistoryCheck(rows) {
  if (!Array.isArray(rows)) return null;
  return rows.find((r) => (r.check_name || r.result?.check_name) === "claim_history") ?? null;
}

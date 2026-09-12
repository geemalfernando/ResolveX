import { useEffect, useMemo, useState } from "react";

import ClaimRiskPanel, { pickClaimHistoryCheck } from "../components/ClaimRiskPanel.jsx";
import { supabase } from "../lib/supabaseClient";

import { api } from "../lib/api";

function riskTone(score) {
  if (score >= 75) return "bg-rose-100 text-rose-800 border-rose-200";
  if (score >= 45) return "bg-amber-100 text-amber-900 border-amber-200";
  if (score >= 20) return "bg-sky-100 text-sky-800 border-sky-200";
  return "bg-emerald-100 text-emerald-800 border-emerald-200";
}

/**
 * Admin claim-risk board: only place that shows CLAIM HISTORY · AI risk %,
 * plus Approve / Deny refund for the selected case.
 */
export default function ClaimRiskBoard() {
  const [rows, setRows] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [ticketsByCase, setTicketsByCase] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  async function loadBoard() {
    setLoading(true);
    const { data: cases } = await supabase
      .from("cases")
      .select("id, order_id, trigger, status, created_at, case_payload")
      .order("created_at", { ascending: false })
      .limit(40);
    if (!cases?.length) {
      setRows([]);
      setTicketsByCase({});
      setLoading(false);
      return;
    }
    const ids = cases.map((c) => c.id);
    const [{ data: checks }, { data: verdicts }, { data: tickets }] = await Promise.all([
      supabase.from("check_results").select("*").in("case_id", ids).eq("check_name", "claim_history"),
      supabase.from("verdicts").select("case_id, outcome, fault_party, confidence").in("case_id", ids),
      supabase.from("support_tickets").select("*").in("case_id", ids),
    ]);
    const checkByCase = Object.fromEntries((checks ?? []).map((c) => [c.case_id, c]));
    const verdictByCase = Object.fromEntries((verdicts ?? []).map((v) => [v.case_id, v]));
    const ticketMap = {};
    for (const t of tickets ?? []) {
      if (!ticketMap[t.case_id] || t.created_at > ticketMap[t.case_id].created_at) {
        ticketMap[t.case_id] = t;
      }
    }
    setTicketsByCase(ticketMap);

    const mapped = cases
      .map((c) => {
        const check = checkByCase[c.id];
        const details = check?.result?.details ?? {};
        const risk = Number(details.risk_score ?? details.risk_probability ?? 0);
        const payload = c.case_payload || {};
        return {
          id: c.id,
          orderId: c.order_id,
          status: c.status,
          customer: payload.customer?.name ?? "Customer",
          customerId: payload.customer?.id,
          complaintType: payload.complaint?.type ?? "other",
          bandHint: payload.complaint?.description?.match(/^\[(\w+)\]/)?.[1] ?? null,
          claims90: details.claims_last_90_days ?? 0,
          flags: details.risk_flags ?? [],
          risk,
          flagged: Boolean(check?.flagged),
          verdict: verdictByCase[c.id],
          check,
        };
      })
      .sort((a, b) => b.risk - a.risk);

    setRows(mapped);
    setLoading(false);
    setSelectedId((prev) => prev ?? mapped[0]?.id ?? null);
  }

  useEffect(() => {
    loadBoard();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const body = await api(`/cases/${selectedId}`);
        if (!cancelled) setDetail(body);
      } catch {
        /* optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const selected = useMemo(() => rows.find((r) => r.id === selectedId), [rows, selectedId]);
  const claimCheck = pickClaimHistoryCheck(detail?.check_results) || selected?.check;
  const ticket = selectedId ? ticketsByCase[selectedId] : null;
  const resolved =
    selected?.status === "resolved" || ticket?.status === "resolved";

  async function decideRefund(decision) {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    const notes =
      decision === "approved"
        ? "Admin approved refund from Claim Risk board."
        : "Admin denied claim from Claim Risk board.";
    try {
      await api(`/cases/${selected.id}/support`, {
        action: decision === "approved" ? "approve_refund" : "reject",
        reason: notes,
      });

      setMessage(
        decision === "approved"
          ? `Refund approved for ${selected.customer}`
          : `Claim denied for ${selected.customer}`
      );
      await loadBoard();
    } catch (err) {
      setMessage(err.message || "Could not save decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <div className="mb-4">
        <h1 className="text-xl font-bold">Claim history · AI</h1>
        <p className="text-sm text-slate-500">
          Risk scores live here only. Select a case to review, then approve or deny the refund.
        </p>
      </div>

      {message && (
        <div className="mb-3 rounded-md border bg-white px-3 py-2 text-sm text-slate-700">{message}</div>
      )}

      {loading && <p className="text-sm text-slate-400">Loading claim cases…</p>}
      {!loading && rows.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-6 text-sm text-slate-500">
          No claim cases yet. From the ResolveX folder run:
          <pre className="mt-2 rounded bg-slate-100 p-3 text-xs overflow-x-auto">
            {`python scripts/seed_data.py --reset
python scripts/seed_claim_cases.py`}
          </pre>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 space-y-2">
          {rows.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              className={`w-full text-left rounded-lg border bg-white px-4 py-3 hover:border-slate-400 ${
                selectedId === r.id ? "border-slate-900 ring-1 ring-slate-900" : ""
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-sm">{r.customer}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {r.bandHint ? `${r.bandHint} · ` : ""}
                    {r.claims90} claims / 90d
                    {r.flags.length ? ` · ${r.flags.join(", ")}` : ""}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {r.verdict?.outcome ?? "—"} · fault {r.verdict?.fault_party ?? "—"}
                    {r.status === "resolved" ? " · resolved" : ""}
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-2.5 py-1 text-sm font-semibold tabular-nums ${riskTone(
                    Math.round(r.risk * 100)
                  )}`}
                >
                  {Math.round(r.risk * 100)}%
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2 space-y-3">
          <ClaimRiskPanel check={claimCheck} />
          {detail?.verdict?.reasons?.length > 0 && (
            <div className="rounded-md border bg-white px-3 py-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Verdict reasons
              </div>
              <ul className="space-y-1.5 text-xs text-slate-600">
                {detail.verdict.reasons.map((r, i) => (
                  <li key={`${r.check}-${i}`}>
                    <span className="font-medium">{r.check}:</span> {r.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selected && (
            <div className="rounded-md border bg-white px-3 py-3 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Admin decision
              </div>
              {resolved ? (
                <p className="text-sm text-slate-600">
                  {ticket?.resolution_notes || "This case is already resolved."}
                </p>
              ) : (
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => decideRefund("approved")}
                    className="rounded-md bg-emerald-600 text-white text-sm px-3 py-1.5 disabled:opacity-50"
                  >
                    {busy ? "Saving…" : "Approve refund"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => decideRefund("denied")}
                    className="rounded-md bg-slate-200 text-slate-800 text-sm px-3 py-1.5 disabled:opacity-50"
                  >
                    Deny claim
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

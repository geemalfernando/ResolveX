import { useEffect, useMemo, useState } from "react";

import ClaimRiskPanel, { AUTO_REFUND_RISK_MAX, pickClaimHistoryCheck } from "../components/ClaimRiskPanel.jsx";
import OutcomeBadge, { outcomeLabel } from "../components/OutcomeBadge.jsx";
import { supabase } from "../lib/supabaseClient";
import { api } from "../lib/api";

function riskTone(score) {
  if (score >= 75) return "bg-rose-50 text-rose-800 ring-rose-200";
  if (score >= AUTO_REFUND_RISK_MAX * 100) return "bg-amber-50 text-amber-900 ring-amber-200";
  return "bg-emerald-50 text-emerald-800 ring-emerald-200";
}

const FILTERS = [
  { id: "review", label: "Needs review" },
  { id: "auto", label: "Auto refund" },
  { id: "resolved", label: "Resolved" },
  { id: "all", label: "All" },
];

function claimDecision(outcome, riskPct) {
  if (outcome === "AUTO_REFUND" || (outcome !== "SUPPORT_TICKET" && riskPct < AUTO_REFUND_RISK_MAX * 100)) {
    return {
      title: "Auto refund",
      blurb: "Refund history looks legitimate, so the refund is issued instantly.",
    };
  }
  if (outcome === "SUPPORT_TICKET" || riskPct >= AUTO_REFUND_RISK_MAX * 100) {
    return {
      title: "Hold for review",
      blurb: "Unusual refund pattern. Approve or deny here. Kitchen disputes stay on Partner.",
    };
  }
  return {
    title: outcomeLabel(outcome),
    blurb: "Claim-history AI scored this account before a refund was issued.",
  };
}

export default function ClaimRiskBoard() {
  const [rows, setRows] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [ticketsByCase, setTicketsByCase] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [filter, setFilter] = useState("review");

  async function loadBoard() {
    setLoading(true);
    const { data: cases } = await supabase
      .from("cases")
      .select("id, order_id, trigger, status, created_at, case_payload")
      .order("created_at", { ascending: false })
      .limit(80);
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
        const verdict = verdictByCase[c.id];
        const needsReview = risk >= AUTO_REFUND_RISK_MAX || verdict?.outcome === "SUPPORT_TICKET";
        return {
          id: c.id,
          orderId: c.order_id,
          status: c.status,
          customer: payload.customer?.name ?? "Customer",
          complaintType: payload.complaint?.type ?? "other",
          claims90: details.claims_last_90_days ?? 0,
          flags: details.risk_flags ?? [],
          risk,
          flagged: Boolean(check?.flagged),
          verdict,
          check,
          needsReview,
        };
      })
      .sort((a, b) => b.risk - a.risk);

    setRows(mapped);
    setLoading(false);
    setSelectedId((prev) => (prev && mapped.some((r) => r.id === prev) ? prev : mapped[0]?.id ?? null));
  }

  useEffect(() => {
    loadBoard();
  }, []);

  useEffect(() => {
    setDetail(null);
    if (!selectedId) return;
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

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      const resolved = r.status === "resolved";
      if (filter === "review") return r.needsReview && !resolved;
      if (filter === "auto") return !r.needsReview;
      if (filter === "resolved") return resolved;
      return true;
    });
  }, [rows, filter]);

  useEffect(() => {
    if (!filtered.length) return;
    if (!filtered.some((r) => r.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = useMemo(
    () => filtered.find((r) => r.id === selectedId) || rows.find((r) => r.id === selectedId),
    [filtered, rows, selectedId]
  );
  const liveDetail = detail?.case_id === selectedId ? detail : null;
  const claimCheck = pickClaimHistoryCheck(liveDetail?.check_results) || selected?.check;
  const ticket = selectedId ? ticketsByCase[selectedId] : null;
  const resolved = selected?.status === "resolved" || ticket?.status === "resolved";
  const outcome = liveDetail?.verdict?.outcome ?? selected?.verdict?.outcome;
  const refund = liveDetail?.case?.workflow?.refund;
  const riskPct = Math.round((selected?.risk ?? 0) * 100);
  const decision = claimDecision(outcome, riskPct);
  const historyReason =
    liveDetail?.verdict?.reasons?.find((r) => r.check === "claim_history")?.reason ||
    claimCheck?.result?.summary ||
    claimCheck?.summary;
  const patternLabel = riskPct >= AUTO_REFUND_RISK_MAX * 100 || selected?.needsReview ? "Unusual" : "Legitimate";
  const counts = {
    review: rows.filter((r) => r.needsReview && r.status !== "resolved").length,
    auto: rows.filter((r) => !r.needsReview).length,
    resolved: rows.filter((r) => r.status === "resolved").length,
    all: rows.length,
  };

  async function decideRefund(choice) {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    const notes =
      choice === "approved"
        ? "Admin approved refund from Claim Risk board."
        : "Admin denied claim from Claim Risk board.";
    try {
      await api(`/cases/${selected.id}/support`, {
        action: choice === "approved" ? "approve_refund" : "reject",
        reason: notes,
      });
      setMessage(choice === "approved" ? `Refund approved for ${selected.customer}` : `Claim denied for ${selected.customer}`);
      await loadBoard();
    } catch (err) {
      setMessage(err.message || "Could not save decision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-3.6rem)] max-w-7xl flex-col px-4 py-4 sm:px-6">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Claim history · AI</p>
          <h1 className="text-2xl font-bold tracking-tight">Refund legitimacy</h1>
          <p className="mt-1 text-sm text-slate-500">
            This board does not assign kitchen or rider fault. It only checks whether the customer’s refund pattern looks legitimate.
            Under {Math.round(AUTO_REFUND_RISK_MAX * 100)}% the refund is issued instantly. {Math.round(AUTO_REFUND_RISK_MAX * 100)}%+ is held here. Partner disputes stay on Partner.
          </p>
        </div>
        <div className="flex flex-wrap gap-1 rounded-full bg-slate-100 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                filter === f.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
              }`}
            >
              {f.label} {counts[f.id] ?? 0}
            </button>
          ))}
        </div>
      </div>

      {message && (
        <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">{message}</div>
      )}

      {loading && <p className="text-sm text-slate-400">Loading claim cases…</p>}
      {!loading && rows.length === 0 && (
        <div className="panel p-6 text-sm text-slate-500">No claim cases yet. Seed demo data, then refresh.</div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12">
        <div className="min-h-0 space-y-2 overflow-y-auto pr-1 lg:col-span-5">
          {filtered.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              className={`w-full rounded-2xl border bg-white p-4 text-left shadow-sm transition ${
                selectedId === r.id ? "border-slate-900 ring-2 ring-slate-900/10" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold">{r.customer}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {r.complaintType.replaceAll("_", " ")} · {r.claims90} claims / 90d
                  </div>
                  <div className="mt-2">
                    <OutcomeBadge outcome={r.verdict?.outcome} />
                  </div>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-sm font-bold tabular-nums ring-1 ${riskTone(Math.round(r.risk * 100))}`}>
                  {Math.round(r.risk * 100)}%
                </span>
              </div>
            </button>
          ))}
          {!loading && filtered.length === 0 && (
            <p className="p-6 text-center text-sm text-slate-500">Nothing in this filter.</p>
          )}
        </div>

        <div className="min-h-0 overflow-y-auto lg:col-span-7">
          {selected ? (
            <div className="space-y-3">
              <section className="panel overflow-hidden">
                <div className="bg-slate-900 px-5 py-4 text-white">
                  <p className="text-xs uppercase tracking-[0.16em] text-teal-200">Refund decision</p>
                  <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
                    <h2 className="text-2xl font-bold">{decision.title}</h2>
                    <span className={`rounded-full px-3 py-1 text-lg font-bold tabular-nums ring-1 ${riskTone(riskPct)}`}>
                      {riskPct}% risk
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">{decision.blurb}</p>
                </div>
                <div className="grid gap-3 p-5 sm:grid-cols-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Customer</p>
                    <p className="font-semibold">{selected.customer}</p>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Refund pattern</p>
                    <p className="font-semibold">{patternLabel}</p>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Refund</p>
                    <p className="font-semibold">
                      {refund
                        ? `LKR ${Number(refund.amount).toLocaleString()} · ${refund.status === "completed" ? "issued instantly" : refund.status}`
                        : selected.needsReview
                          ? "Held"
                          : "Not issued"}
                    </p>
                  </div>
                </div>
                <div className="border-t px-5 py-4">
                  {resolved ? (
                    <p className="text-sm text-slate-600">
                      {ticket?.resolution_notes ||
                        (outcome === "AUTO_REFUND"
                          ? "Refund already issued automatically."
                          : "This case is already resolved.")}
                    </p>
                  ) : selected.needsReview ? (
                    <div className="flex flex-wrap gap-2">
                      <button type="button" disabled={busy} onClick={() => decideRefund("approved")} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                        {busy ? "Saving…" : "Approve refund"}
                      </button>
                      <button type="button" disabled={busy} onClick={() => decideRefund("denied")} className="btn-secondary">
                        Deny claim
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm font-medium text-emerald-800">
                      Risk is under {Math.round(AUTO_REFUND_RISK_MAX * 100)}%, so the refund is automatic.
                    </p>
                  )}
                </div>
              </section>

              <ClaimRiskPanel check={claimCheck} />

              {historyReason && (
                <section className="panel p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Why this result</h3>
                  <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">{historyReason}</p>
                </section>
              )}
            </div>
          ) : (
            <div className="panel grid h-full place-items-center p-8 text-sm text-slate-500">Select a case to see the decision.</div>
          )}
        </div>
      </div>
    </div>
  );
}

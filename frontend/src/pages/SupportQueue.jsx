import { useEffect, useMemo, useState } from "react";

import CasePanel from "../components/CasePanel.jsx";
import { api } from "../lib/api";

const ACTIONS = [
  ["confirm", "Confirm AI verdict"],
  ["merchant", "Merchant responsible"],
  ["rider", "Rider responsible"],
  ["neither", "Neither responsible"],
  ["request_evidence", "Request more evidence"],
  ["approve_refund", "Approve refund"],
  ["reject", "Reject claim"],
];

export default function SupportQueue() {
  const [data, setData] = useState({ count: 0, cases: [] });
  const [selectedId, setSelectedId] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = async () => {
    try {
      const next = await api("/workflow/support");
      setData(next);
      setSelectedId((current) => {
        if (current && next.cases.some((record) => record.case_id === current)) return current;
        return next.cases[0]?.case_id ?? null;
      });
      setError("");
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  const selected = useMemo(
    () => data.cases.find((record) => record.case_id === selectedId) ?? data.cases[0] ?? null,
    [data, selectedId],
  );

  async function act(action) {
    if (!selected) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/cases/${selected.case_id}/support`, { action, reason: reason.trim() });
      setMessage("Support decision saved.");
      setReason("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Support</p>
          <h1 className="text-2xl font-bold tracking-tight">Case review queue</h1>
          <p className="mt-1 text-sm text-slate-500">
            Review customer, merchant, rider, timing, zone and model evidence before resolving a dispute.
          </p>
        </div>
        <div className="rounded-full bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white">
          {data.count} open
        </div>
      </div>

      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {message && <p className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p>}

      <div className="grid min-h-[34rem] gap-4 lg:grid-cols-12">
        <aside className="space-y-2 overflow-y-auto lg:col-span-4">
          {data.cases.map((record) => {
            const risk = Math.round((record.claim_risk?.risk_score ?? 0) * 100);
            return (
              <button
                type="button"
                key={record.case_id}
                onClick={() => { setSelectedId(record.case_id); setReason(""); }}
                className={`w-full rounded-2xl border bg-white p-4 text-left transition ${selected?.case_id === record.case_id ? "border-slate-900 shadow-sm" : "border-slate-200 hover:border-slate-400"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold">Case {record.case_id.slice(0, 8).toUpperCase()}</p>
                    <p className="mt-1 text-xs text-slate-500">{record.case?.customer?.name} · order {record.case?.order?.id?.slice(0, 8)}</p>
                  </div>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${risk >= 55 ? "bg-rose-100 text-rose-800" : risk >= 35 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                    risk {risk}%
                  </span>
                </div>
                <p className="mt-2 text-xs text-slate-600">{record.case?.workflow?.partner?.status === "disputed" ? "Partner dispute" : record.verdict?.outcome?.replaceAll("_", " ") ?? "Awaiting assessment"}</p>
              </button>
            );
          })}
          {!data.cases.length && (
            <div className="rounded-2xl border border-dashed bg-white p-6 text-sm text-slate-500">
              No cases require support review.
            </div>
          )}
        </aside>

        <section className="panel min-h-0 overflow-y-auto p-5 lg:col-span-8">
          {selected ? (
            <div className="space-y-5">
              <CasePanel record={selected} technical />

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <h2 className="font-semibold">Support decision</h2>
                <p className="mt-1 text-xs text-slate-500">
                  An explanation is required for overrides, rejection and evidence requests.
                </p>
                <textarea
                  className="field mt-3"
                  placeholder="Decision / override reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  {ACTIONS.map(([action, label]) => (
                    <button
                      key={action}
                      type="button"
                      disabled={busy}
                      className={action === "approve_refund" ? "btn" : "btn-secondary"}
                      onClick={() => act(action)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Select a case to review.</p>
          )}
        </section>
      </div>
    </div>
  );
}

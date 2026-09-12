import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import CasePanel from "../components/CasePanel";
import OutcomeBadge from "../components/OutcomeBadge.jsx";

export default function PartnerPortal() {
  const [records, setRecords] = useState([]);
  const [tab, setTab] = useState("Needs Response");
  const [selectedId, setSelectedId] = useState(null);
  const [reasons, setReasons] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api("/workflow/cases").then(setRecords).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function respond(id, action) {
    setBusy(true);
    setError("");
    try {
      await api(`/cases/${id}/partner`, { action, reason: reasons[id] ?? "" });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const status = (r) =>
    r.case.workflow?.partner?.status === "disputed"
      ? "Disputed"
      : r.status === "resolved" || r.case.workflow?.partner?.status === "accepted"
        ? "Resolved"
        : "Needs Response";

  const filtered = useMemo(
    () => records.filter((r) => r.verdict && status(r) === tab),
    [records, tab]
  );
  const selected = filtered.find((r) => r.case_id === selectedId) || filtered[0];

  return (
    <div className="mx-auto flex h-[calc(100vh-3.6rem)] max-w-7xl flex-col px-4 py-4 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Restaurant</p>
      <h1 className="text-2xl font-bold tracking-tight">Partner response</h1>
      <p className="mt-1 text-sm text-slate-500">Accept or dispute the decision on cases for your kitchen.</p>
      <div className="my-3 flex gap-1 rounded-full bg-slate-100 p-1 w-fit">
        {["Needs Response", "Resolved", "Disputed"].map((t) => (
          <button className={`rounded-full px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-white shadow-sm" : "text-slate-500"}`} key={t} onClick={() => { setTab(t); setSelectedId(null); }}>
            {t}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12">
        <aside className="min-h-0 space-y-2 overflow-y-auto lg:col-span-4">
          {filtered.map((r) => (
            <button
              key={r.case_id}
              className={`w-full rounded-2xl border bg-white p-4 text-left ${selected?.case_id === r.case_id ? "border-slate-900" : "border-slate-200"}`}
              onClick={() => setSelectedId(r.case_id)}
            >
              <div className="flex items-center justify-between gap-2">
                <b className="text-sm">Order {r.case.order.id.slice(0, 8)}</b>
                <OutcomeBadge outcome={r.verdict?.outcome} />
              </div>
            </button>
          ))}
          {!filtered.length && <p className="text-sm text-slate-500">No cases in this tab.</p>}
        </aside>
        <article className="panel min-h-0 overflow-y-auto p-5 lg:col-span-8">
          {selected ? (
            <>
              <CasePanel record={selected} />
              <label className="mt-4 block text-sm font-medium">
                Response
                <textarea className="field" value={reasons[selected.case_id] ?? ""} onChange={(e) => setReasons({ ...reasons, [selected.case_id]: e.target.value })} />
              </label>
              <div className="mt-3 flex gap-2">
                <button disabled={busy} className="btn" onClick={() => respond(selected.case_id, "accept")}>Accept verdict</button>
                <button disabled={busy || !reasons[selected.case_id]?.trim()} className="btn-secondary" onClick={() => respond(selected.case_id, "dispute")}>Dispute</button>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">Select a case to respond.</p>
          )}
        </article>
      </div>
    </div>
  );
}

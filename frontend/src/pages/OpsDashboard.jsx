import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../auth/AuthContext";
import MapView from "../components/MapView";
import OutcomeBadge from "../components/OutcomeBadge.jsx";

export default function OpsDashboard() {
  const { role } = useAuth();
  const [ops, setOps] = useState(null);
  const [feed, setFeed] = useState(null);
  const [positions, setPositions] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    Promise.all([api("/workflow/ops"), api("/demo/state"), api("/workflow/ops/positions")])
      .then(([o, f, p]) => {
        setOps(o);
        setFeed(f);
        setPositions(p);
        setError("");
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function control(action) {
    setBusy(true);
    setError("");
    try {
      setFeed(await api("/demo/control", { action }));
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Operations</p>
          <h1 className="text-2xl font-bold tracking-tight">Live delivery control</h1>
          <p className="mt-1 text-sm text-slate-500">Late orders create incidents before a customer complaint arrives.</p>
        </div>
        <button className="btn-secondary" onClick={load}>Refresh</button>
      </div>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        {Object.entries(ops?.counts ?? {}).map(([k, v]) => (
          <div className="panel p-3" key={k}>
            <p className="text-[11px] capitalize text-slate-500">{k.replaceAll("_", " ")}</p>
            <b className="text-xl">{v}</b>
          </div>
        ))}
      </div>

      {(ops?.zone_incidents?.length ?? 0) > 0 && (
        <section className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Active zone incidents</h2>
              <p className="text-xs text-slate-500">Shared disruption is treated as neither merchant nor rider fault.</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {ops.zone_incidents.map((zone) => (
              <article key={zone.id} className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <b>{zone.zone_id}</b>
                  <span className="rounded-full bg-amber-200/70 px-2 py-1 text-[11px] font-semibold text-amber-900">broadcast active</span>
                </div>
                <p className="mt-2 text-amber-950/80">{zone.late_orders ?? 0} late / {zone.active_orders ?? 0} active</p>
                <p className="text-amber-950/80">{zone.customers_notified ?? 0} customers notified</p>
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="grid min-h-[31rem] gap-4 lg:grid-cols-2">
        <section className="panel flex min-h-0 flex-col p-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Mock busy-evening feed</h2>
              <p className="text-xs text-slate-500">Run the feed to demonstrate proactive detection.</p>
            </div>
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${feed?.running ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
              {feed?.running ? "Running" : "Paused"}
            </span>
          </div>
          <div className="my-3 flex flex-wrap gap-2">
            {[["start", "Start busy evening"], ["pause", "Pause"], ["reset", "Reset demo"], ["step", "Next stage"]].map(([a, l]) => (
              <button className="btn-secondary" disabled={busy} key={a} onClick={() => control(a)}>{l}</button>
            ))}
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-auto">
            {feed?.orders?.map((o) => (
              <div key={o.id} className={`rounded-xl border-l-4 bg-slate-50 p-3 ${o.late ? "border-rose-500" : o.stage === "READY" ? "border-amber-400" : "border-emerald-500"}`}>
                <div className="flex justify-between gap-3 text-sm font-semibold">
                  <span>{o.scenario} · {o.id.slice(0, 8)}</span>
                  <span>{o.stage}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  ETA {o.eta_minutes ?? "pending"} · {o.late ? "Late" : "On track"}
                  {o.case_id ? ` · incident ${o.case_id.slice(0, 8)} created` : " · no incident"}
                </p>
                {o.case_id && !o.complaint_exists && (
                  <p className="mt-1 text-xs font-medium text-teal-800">Detected before complaint</p>
                )}
              </div>
            ))}
            {!feed?.orders?.length && <p className="py-8 text-center text-sm text-slate-500">Start the busy-evening feed to create live demo orders.</p>}
          </div>
        </section>
        <div className="panel min-h-[22rem] overflow-hidden"><MapView orders={positions} /></div>
      </div>

      <section className="panel max-h-72 overflow-auto p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">Recent incidents</h2>
          {(role === "admin" || role === "support") && (
            <Link to="/claims" className="text-sm font-medium text-teal-800">Claim Risk</Link>
          )}
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {ops?.cases?.slice(0, 12).map((c) => (
            <article className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm" key={c.case_id}>
              <div>
                <span className="font-medium">Order {c.case?.order?.id?.slice(0, 8)}</span>
                <p className="text-xs text-slate-500">{c.case?.complaint ? "Customer complaint" : "Proactive incident"}</p>
              </div>
              <OutcomeBadge outcome={c.verdict?.outcome} />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

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
    <div className="mx-auto flex h-[calc(100vh-3.6rem)] max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Operations</p>
          <h1 className="text-2xl font-bold tracking-tight">Live deliveries</h1>
        </div>
        <button className="btn-secondary" onClick={load}>Refresh</button>
      </div>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
        {Object.entries(ops?.counts ?? {}).map(([k, v]) => (
          <div className="panel p-3" key={k}>
            <p className="text-[11px] capitalize text-slate-500">{k.replaceAll("_", " ")}</p>
            <b className="text-xl">{v}</b>
          </div>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <section className="panel flex min-h-0 flex-col p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Live feed</h2>
            <span className="text-xs text-slate-500">{feed?.running ? "Running" : "Paused"}</span>
          </div>
          <div className="my-3 flex flex-wrap gap-2">
            {[["start", "Start"], ["pause", "Pause"], ["reset", "Reset"], ["step", "Next"]].map(([a, l]) => (
              <button className="btn-secondary" disabled={busy} key={a} onClick={() => control(a)}>{l}</button>
            ))}
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-auto">
            {feed?.orders?.map((o) => (
              <div key={o.id} className={`rounded-xl border-l-4 bg-slate-50 p-3 ${o.late ? "border-rose-500" : o.stage === "READY" ? "border-amber-400" : "border-emerald-500"}`}>
                <div className="flex justify-between text-sm font-semibold">
                  <span>{o.scenario} · {o.id.slice(0, 8)}</span>
                  <span>{o.stage}</span>
                </div>
                <p className="text-xs text-slate-500">ETA {o.eta_minutes ?? "pending"} · {o.late ? "Late" : "On track"}</p>
              </div>
            ))}
          </div>
        </section>
        <div className="panel min-h-[18rem] overflow-hidden"><MapView orders={positions} /></div>
      </div>

      <section className="panel max-h-52 overflow-auto p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">Cases</h2>
          {(role === "admin" || role === "support") && (
            <Link to="/claims" className="text-sm font-medium text-teal-800">Claim Risk</Link>
          )}
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {ops?.cases?.slice(0, 8).map((c) => (
            <article className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm" key={c.case_id}>
              <span>Order {c.case?.order?.id?.slice(0, 8)}</span>
              <OutcomeBadge outcome={c.verdict?.outcome} />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

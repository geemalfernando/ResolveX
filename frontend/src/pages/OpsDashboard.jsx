import { useEffect, useState } from "react";

import MapView from "../components/MapView.jsx";
import { supabase } from "../lib/supabaseClient";

/**
 * Ops team view: live map + case feed (outcomes only — claim risk % lives on /claims).
 */
export default function OpsDashboard() {
  const [cases, setCases] = useState([]);
  const [verdicts, setVerdicts] = useState({});

  useEffect(() => {
    let isMounted = true;

    async function loadCases() {
      const { data, error } = await supabase
        .from("cases")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(40);
      if (error || !isMounted) return;
      setCases(data ?? []);

      if (data?.length) {
        const ids = data.map((c) => c.id);
        const { data: verdictRows } = await supabase
          .from("verdicts")
          .select("case_id, outcome, fault_party, confidence")
          .in("case_id", ids);
        if (!isMounted) return;
        const vmap = {};
        for (const v of verdictRows ?? []) vmap[v.case_id] = v;
        setVerdicts(vmap);
      }
    }
    loadCases();

    const channel = supabase
      .channel("cases-realtime")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "cases" }, (payload) => {
        setCases((prev) => [payload.new, ...prev].slice(0, 40));
      })
      .subscribe();

    return () => {
      isMounted = false;
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 rounded-lg overflow-hidden border h-[70vh]">
        <MapView />
      </div>

      <div className="rounded-lg border bg-white p-4 flex flex-col gap-3 max-h-[70vh]">
        <h2 className="font-semibold">Live cases</h2>
        <ul className="space-y-2 overflow-y-auto flex-1">
          {cases.length === 0 && <li className="text-sm text-slate-400">No cases yet.</li>}
          {cases.map((c) => {
            const v = verdicts[c.id];
            const abuse = v?.fault_party === "customer_abuse";
            const support = v?.outcome === "SUPPORT_TICKET";
            return (
              <li key={c.id} className="rounded-md border px-3 py-2 text-sm">
                <div className="font-medium flex items-center justify-between gap-2">
                  <span>Order {String(c.order_id).slice(0, 8)}…</span>
                  <span className="flex items-center gap-1">
                    {abuse && (
                      <span className="text-[10px] rounded-full bg-rose-100 text-rose-800 px-1.5 py-0.5">
                        fraud
                      </span>
                    )}
                    {!abuse && support && (
                      <span className="text-[10px] rounded-full bg-amber-100 text-amber-800 px-1.5 py-0.5">
                        review
                      </span>
                    )}
                  </span>
                </div>
                <div className="text-slate-500">
                  {c.trigger} · {v?.outcome ?? c.status}
                </div>
              </li>
            );
          })}
        </ul>
        <p className="text-xs text-slate-400 border-t pt-2">
          Claim risk scores and Approve/Deny are on the Claim Risk page.
        </p>
      </div>
    </div>
  );
}

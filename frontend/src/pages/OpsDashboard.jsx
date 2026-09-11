import { useEffect, useState } from "react";

import MapView from "../components/MapView.jsx";
import { supabase } from "../lib/supabaseClient";

/**
 * Ops team view: live map of open orders + a feed of late/failed/disputed cases.
 * Subscribes to Supabase Realtime on `cases` so new flagged cases appear without a refresh.
 */
export default function OpsDashboard() {
  const [cases, setCases] = useState([]);

  useEffect(() => {
    let isMounted = true;

    async function loadCases() {
      const { data, error } = await supabase
        .from("cases")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(20);
      if (!error && isMounted) setCases(data ?? []);
    }
    loadCases();

    const channel = supabase
      .channel("cases-realtime")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "cases" }, (payload) => {
        setCases((prev) => [payload.new, ...prev].slice(0, 20));
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

      <div className="rounded-lg border bg-white p-4">
        <h2 className="font-semibold mb-3">Live cases</h2>
        <ul className="space-y-2 max-h-[65vh] overflow-y-auto">
          {cases.length === 0 && <li className="text-sm text-slate-400">No cases yet.</li>}
          {cases.map((c) => (
            <li key={c.id} className="rounded-md border px-3 py-2 text-sm">
              <div className="font-medium">Order {c.order_id}</div>
              <div className="text-slate-500">{c.trigger} · {c.status}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";

import { supabase } from "../lib/supabaseClient";

/**
 * Support agent queue: cases whose verdict outcome was SUPPORT_TICKET (low confidence or
 * disputed fault), i.e. the human-in-the-loop cases.
 */
export default function SupportQueue() {
  const [tickets, setTickets] = useState([]);

  useEffect(() => {
    async function loadTickets() {
      const { data, error } = await supabase
        .from("support_tickets")
        .select("*, cases(*)")
        .order("created_at", { ascending: false });
      if (!error) setTickets(data ?? []);
    }
    loadTickets();

    const channel = supabase
      .channel("support-tickets-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "support_tickets" },
        (payload) => setTickets((prev) => [payload.new, ...prev])
      )
      .subscribe();

    return () => supabase.removeChannel(channel);
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-4">Support queue</h1>

      <div className="space-y-3">
        {tickets.length === 0 && <p className="text-sm text-slate-400">No open tickets — nice.</p>}
        {tickets.map((t) => (
          <div key={t.id} className="rounded-lg border bg-white p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">Case {t.case_id}</div>
                <div className="text-sm text-slate-500">Status: {t.status}</div>
              </div>
              <span className="text-xs rounded-full bg-amber-100 text-amber-800 px-2 py-1">
                needs review
              </span>
            </div>
            <div className="mt-3 flex gap-2">
              <button className="rounded-md bg-emerald-600 text-white text-sm px-3 py-1.5">
                Approve refund
              </button>
              <button className="rounded-md bg-slate-200 text-slate-800 text-sm px-3 py-1.5">
                Deny claim
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

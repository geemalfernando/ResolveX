import { useEffect, useState } from "react";

import { supabase } from "../lib/supabaseClient";

/**
 * Merchant-facing view: complaints tied to this merchant's orders, with a place to respond.
 * TODO: scope the query to the logged-in merchant once Supabase Auth is wired up
 * (filter cases by case_payload->order->merchant->id or a merchant_id column).
 */
export default function PartnerPortal() {
  const [cases, setCases] = useState([]);

  useEffect(() => {
    async function loadCases() {
      const { data, error } = await supabase
        .from("cases")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(20);
      if (!error) setCases(data ?? []);
    }
    loadCases();
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-4">Complaints on your orders</h1>

      <div className="space-y-3">
        {cases.length === 0 && <p className="text-sm text-slate-400">No complaints yet.</p>}
        {cases.map((c) => (
          <div key={c.id} className="rounded-lg border bg-white p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">Order {c.order_id}</div>
                <div className="text-sm text-slate-500">{c.trigger}</div>
              </div>
              <span className="text-xs rounded-full bg-slate-100 px-2 py-1">{c.status}</span>
            </div>
            <textarea
              placeholder="Respond to this complaint..."
              rows={2}
              className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
            <button className="mt-2 rounded-md bg-slate-900 text-white text-sm px-3 py-1.5">
              Send response
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

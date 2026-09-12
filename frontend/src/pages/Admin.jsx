import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import RiderAccounts from "../components/RiderAccounts";

function riskBadge(score = 0) {
  const pct = Math.round(Number(score || 0) * 100);
  const cls = pct >= 55 ? "bg-rose-100 text-rose-800" : pct >= 35 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800";
  return <span className={`rounded-full px-2 py-1 text-xs font-semibold ${cls}`}>{pct}%</span>;
}

export default function Admin() {
  const [data, setData] = useState(null);
  const [models, setModels] = useState(null);
  const [error, setError] = useState("");

  const load = () => api("/workflow/admin").then(setData).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    api("/api/model/status").then(setModels).catch((e) => setError(e.message));
    return () => clearInterval(timer);
  }, []);

  async function flag(id, manual_review) {
    try {
      await api(`/workflow/admin/customers/${id}`, { manual_review });
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const refunds = data?.refunds ?? [];
  const reviews = data?.fraud_reviews ?? [];
  const accounts = (data?.accounts ?? []).filter((account) => account.claims > 0);

  return (
    <div className="page-shell space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Administration</p>
          <h1 className="text-2xl font-bold tracking-tight">Control center</h1>
          <p className="mt-1 text-sm text-slate-500">Monitor refunds, AI claim risk, account flags and human-review feedback.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/support" className="btn-secondary">Support queue</Link>
          <Link to="/claims" className="btn">Open Claim Risk</Link>
        </div>
      </div>

      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ["Reviewed", data?.reviewed_cases],
          ["Overrides", data?.overrides],
          ["AI agreement", data?.agreement_rate == null ? "—" : `${(data.agreement_rate * 100).toFixed(0)}%`],
          ["Claim risk review", reviews.length],
        ].map(([label, value]) => (
          <div key={label} className="panel p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            <b className="mt-1 block text-2xl tracking-tight">{value ?? 0}</b>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel flex max-h-[22rem] flex-col p-5">
          <h2 className="font-semibold">Refunds</h2>
          <p className="text-xs text-slate-500">Automatically resolved claims and support-approved refunds.</p>
          <div className="mt-3 min-h-0 flex-1 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-white text-xs uppercase text-slate-400">
                <tr>{["Customer", "Ref", "Amount", "Status"].map((h) => <th className="py-2" key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {refunds.map((r) => (
                  <tr className="border-t border-slate-100" key={`${r.case_id}-${r.reference}`}>
                    <td className="py-2">{r.customer}</td>
                    <td className="font-mono text-xs">{r.reference}</td>
                    <td>{r.currency} {Number(r.amount).toLocaleString()}</td>
                    <td className="capitalize">{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!refunds.length && <p className="py-6 text-sm text-slate-500">No refunds yet.</p>}
          </div>
        </section>

        <section className="panel flex max-h-[22rem] flex-col p-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Claim Risk · AI</h2>
              <p className="text-xs text-slate-500">High-risk open claims are routed to review, not automatically rejected.</p>
            </div>
            <Link to="/claims" className="text-sm font-medium text-teal-800">Full board</Link>
          </div>
          <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-auto">
            {reviews.map((r) => (
              <div key={r.case_id} className="rounded-xl bg-amber-50 px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <b>{r.customer}</b>
                  {riskBadge(r.risk_score)}
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  {r.claims_last_90_days ?? 0} claims / 90d{r.risk_flags?.length ? ` · ${r.risk_flags.join(", ")}` : ""}
                </p>
              </div>
            ))}
            {!reviews.length && <p className="py-6 text-sm text-slate-500">No claims waiting for risk review.</p>}
          </div>
        </section>
      </div>

      <section className="panel overflow-hidden">
        <div className="border-b px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">Customer claim-risk monitoring</h2>
              <p className="text-xs text-slate-500">The risk model affects review routing, not operational fault attribution.</p>
            </div>
            <Link to="/claims" className="text-sm font-medium text-teal-800">Review cases</Link>
          </div>
        </div>
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-400">
              <tr>{["Customer", "Orders", "Claims", "Refunds", "AI risk", "Signals", "Status", ""].map((title) => <th className="px-4 py-2" key={title}>{title}</th>)}</tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-medium">{account.name}</td>
                  <td>{account.orders}</td>
                  <td>{account.claims}</td>
                  <td>{account.refunds}</td>
                  <td>{riskBadge(account.claim_risk?.risk_score)}</td>
                  <td className="max-w-52 text-xs text-slate-500">{account.claim_risk?.risk_flags?.join(", ") || "Normal pattern"}</td>
                  <td>{account.manual_review ? "Manual review" : account.claim_risk?.flagged ? "Review suggested" : "Normal"}</td>
                  <td className="px-4 py-2">
                    <button className="btn-secondary" onClick={() => flag(account.id, !account.manual_review)}>
                      {account.manual_review ? "Clear" : "Flag"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!accounts.length && <p className="p-5 text-sm text-slate-500">No customer claim history yet.</p>}
        </div>
      </section>

      <RiderAccounts />

      <details className="panel p-4 text-sm">
        <summary className="cursor-pointer font-medium">Model status</summary>
        <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-slate-50 p-3 text-xs">{JSON.stringify(models, null, 2)}</pre>
      </details>
    </div>
  );
}

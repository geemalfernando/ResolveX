import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import RiderAccounts from "../components/RiderAccounts";
import ClaimRiskBoard from "./ClaimRiskBoard.jsx";

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

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">System administration</h1>
          <p className="mt-1 text-sm text-slate-500">
            Review human overrides, repeat faults, refund-abuse signals, and AI claim risk.
          </p>
        </div>
        <Link to="/claims" className="btn-secondary">
          Open full Claim Risk board
        </Link>
      </div>

      {error && <p role="alert" className="text-red-700">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          ["Reviewed cases", data?.reviewed_cases],
          ["Overrides", data?.overrides],
          ["AI agreement", data?.agreement_rate == null ? "—" : `${(data.agreement_rate * 100).toFixed(1)}%`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border bg-white p-5">
            <p>{label}</p>
            <b className="text-2xl">{value ?? 0}</b>
          </div>
        ))}
      </div>

      <RiderAccounts />
      <section className="rounded-xl border bg-white p-5 space-y-4">
        <h2 className="font-semibold">Automated refunds & fraud screening</h2>
        <p className="text-sm text-slate-500">Eligible claims receive demo refunds automatically. Unusual claim history pauses automatic refunds for support review; it does not prove fraud.</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="rounded-lg bg-emerald-50 p-4"><b>{new Set((data?.refunds ?? []).map(r => r.reference)).size} refunds completed</b><p className="text-xs">Simulated payments · no money transferred</p></div>
          <div className="rounded-lg bg-amber-50 p-4"><b>{data?.fraud_reviews?.length ?? 0} claims need risk review</b><p className="text-xs">Screened automatically on every analysis</p></div>
        </div>
        <h3 className="font-medium">Refund activity</h3>
        <div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr>{['Customer', 'Reference', 'Amount', 'Status'].map(h => <th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>
          {(data?.refunds ?? []).map(r => <tr className="border-t" key={r.case_id}><td className="p-2">{r.customer}</td><td>{r.reference}</td><td>{r.currency} {Number(r.amount).toLocaleString()}</td><td>{r.status}</td></tr>)}
        </tbody></table>{!data?.refunds?.length && <p className="text-sm text-slate-500">No refunds completed yet.</p>}</div>
        <h3 className="font-medium">Suspected claim abuse — needs review</h3>
        {(data?.fraud_reviews ?? []).map(r => <div key={r.case_id} className="rounded border border-amber-200 p-3 text-sm"><b>{r.customer}</b><p>{r.summary}</p><p className="text-xs text-slate-500">{r.claims_last_90_days ?? 'Unknown'} prior claims · {r.source === 'rules' ? 'Rule-based screening' : r.source} · Support review required</p></div>)}
        {!data?.fraud_reviews?.length && <p className="text-sm text-slate-500">No claims currently flagged for risk review.</p>}
      </section>

      <section className="rounded-xl border bg-white p-5 overflow-auto">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h2 className="font-semibold">Claim abuse monitoring</h2>
            <p className="text-xs text-slate-500">
              Account-level frequency signals. Detailed ML claim-risk probabilities are shown below.
            </p>
          </div>
          <Link to="/claims" className="text-sm font-medium text-slate-700 underline">
            View dedicated Claim Risk page
          </Link>
        </div>
        <table className="w-full text-sm text-left">
          <thead>
            <tr>
              {['Customer', 'Orders', 'Claims', 'Refunds', 'Review', 'Action'].map((title) => (
                <th className="p-2" key={title}>{title}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.accounts
              .filter((account) => account.claims > 0)
              .map((account) => (
                <tr key={account.id} className="border-t">
                  <td className="p-2">{account.name}</td>
                  <td>{account.orders}</td>
                  <td>{account.claims}</td>
                  <td>{account.refunds}</td>
                  <td>
                    {account.manual_review
                      ? 'Manual review'
                      : account.claims >= 3
                        ? 'Review suggested'
                        : 'Low frequency'}
                  </td>
                  <td>
                    <button
                      className="btn-secondary my-2"
                      onClick={() => flag(account.id, !account.manual_review)}
                    >
                      {account.manual_review ? 'Clear flag' : 'Require manual review'}
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <p className="text-xs text-slate-500 mt-2">
          Flags request review. No automatic permanent penalties are applied.
        </p>
      </section>

      <section className="rounded-xl border bg-white overflow-hidden">
        <div className="border-b bg-slate-50 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold">Claim Risk · AI</h2>
              <p className="text-xs text-slate-500 mt-1">
                Claim-history model signals are available here for administrators and on the dedicated Claim Risk page.
              </p>
            </div>
            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
              Admin monitoring
            </span>
          </div>
        </div>
        <ClaimRiskBoard />
      </section>

      <section className="rounded-xl border bg-white p-5">
        <h2 className="font-semibold">Human-confirmed repeat faults</h2>
        <pre className="text-xs overflow-auto mt-2">{JSON.stringify(data?.repeat_faults, null, 2)}</pre>
      </section>

      <details className="rounded-xl border bg-white p-5">
        <summary>Model and dataset information</summary>
        <pre className="text-xs overflow-auto mt-3">{JSON.stringify(models, null, 2)}</pre>
      </details>
    </div>
  );
}

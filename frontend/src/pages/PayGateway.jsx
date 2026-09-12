import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../lib/api";

export default function PayGateway() {
  const { orderId } = useParams();
  const { profile } = useAuth();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/commerce/orders/${orderId}`).then(setOrder).catch((e) => setError(e.message));
  }, [orderId]);

  const payment = order?.items?.[0]?.payment;
  const total = (order?.items ?? []).reduce((sum, item) => sum + item.qty * item.price, 0);
  const paid = payment?.status === "captured";

  async function pay() {
    setBusy(true);
    setError("");
    try {
      const updated = await api(`/commerce/orders/${orderId}/pay`, {
        holder: profile?.display_name || "Demo Customer",
      });
      setOrder(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center bg-slate-100 px-4 py-10">
      <div className="w-full max-w-md overflow-hidden rounded-3xl bg-white shadow-xl ring-1 ring-slate-200">
        <div className="bg-slate-950 px-6 py-5 text-white">
          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-teal-300">ResolveX Pay</p>
          <h1 className="mt-2 text-2xl font-black">{paid ? "Payment received" : "Pay for your order"}</h1>
          {order && <p className="mt-1 text-sm text-slate-400">Order {order.id.slice(0, 8).toUpperCase()}</p>}
        </div>

        <div className="space-y-5 p-6">
          {error && <p role="alert" className="rounded-2xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

          {!order && !error && <p className="text-sm text-slate-500">Loading gateway…</p>}

          {order && (
            <>
              <ul className="divide-y rounded-2xl bg-slate-50 px-4 text-sm">
                {order.items.map((item, index) => (
                  <li key={index} className="flex justify-between py-2">
                    <span>{item.qty} × {item.name}</span>
                    <span>LKR {(item.qty * item.price).toLocaleString()}</span>
                  </li>
                ))}
                <li className="flex justify-between py-2 font-black">
                  <span>Total</span>
                  <span>LKR {total.toLocaleString()}</span>
                </li>
              </ul>

              {paid ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
                  <p className="font-bold text-emerald-900">Paid to {payment.account || "Visa ••4242"}</p>
                  <p className="mt-1 text-emerald-800">Refunds from claims return to this account.</p>
                </div>
              ) : (
                <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                  <p className="font-bold text-slate-900">Demo card · Visa ••4242</p>
                  <p className="mt-1 text-slate-500">One tap pays this order. Nothing is charged live.</p>
                </div>
              )}

              {paid ? (
                <Link to="/my-orders" className="btn w-full py-3 text-center">View order</Link>
              ) : (
                <button className="btn w-full py-3" disabled={busy} onClick={pay}>
                  {busy ? "Paying…" : `Pay LKR ${total.toLocaleString()}`}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { actionLabel, api, resolution, uploadApi } from "../lib/api";
import { preparePhoto } from "../lib/photo";
import CasePanel from "../components/CasePanel";
import OutcomeBadge from "../components/OutcomeBadge.jsx";

const ISSUES = [
  { id: "late", icon: "⏱️", label: "Late delivery", hint: "Arrived after the promised time.", photo: false, photoHint: "A timestamped photo is optional." },
  { id: "damaged", icon: "📦", label: "Damaged order", hint: "Packaging, seal, or food was damaged.", photo: true, photoHint: "Photo of the damage, plus the bag if you still have it." },
  { id: "wrong_item", icon: "🍛", label: "Wrong item", hint: "You received a different dish or order.", photo: true, photoHint: "Photo of what arrived, including labels if visible." },
  { id: "missing_item", icon: "➖", label: "Missing item", hint: "Something from the order was not in the bag.", photo: true, photoHint: "Photo of the bag contents you received." },
  { id: "not_delivered", icon: "📍", label: "Not delivered", hint: "Marked delivered but you never received it.", photo: false, photoHint: "A photo of the drop-off area is optional." },
  { id: "tampering", icon: "🔒", label: "Possible tampering", hint: "Seal broken or packaging looks opened.", photo: true, photoHint: "Photo of the seal, lid, or opened packaging." },
];

const STATUS = {
  placed: "Placed",
  preparing: "Preparing",
  ready: "Packed",
  picked_up: "With rider",
  dropped_off: "Delivered",
  completed: "Completed",
  cancelled: "Cancelled",
};

const CHECKS = [
  ["⏱️", "Timing", "Prep and delivery minutes vs the promise."],
  ["📷", "Photos", "Packing, handover, and your claim photo."],
  ["📍", "Route", "Rider GPS for detours, stops, and drop-off."],
  ["🌐", "Zone", "Whether the area had a shared delay."],
  ["⚖️", "Refund pattern", "Whether this account’s claims look legitimate."],
];

const ORDER_ID_PATTERN = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const isOrderId = (value) => new RegExp(`^${ORDER_ID_PATTERN}$`).test(value);

function merchantTitle(name = "") {
  return name.split(" · ")[0] || "Restaurant";
}

function orderTotal(order) {
  return (order?.items ?? []).reduce((sum, item) => sum + item.qty * item.price, 0);
}

function paymentOf(order) {
  return order?.items?.[0]?.payment;
}

function deliveryOf(order) {
  return order?.items?.[0]?.delivery;
}

function nextStepCopy(record) {
  const outcome = resolution(record);
  const refund = record?.case?.workflow?.refund;
  const dest = refund?.destination || refund?.account;
  if (outcome === "AUTO_REFUND" && refund) {
    return `The refund of LKR ${Number(refund.amount).toLocaleString()} is issued to ${dest || "your ResolveX Pay account"}.`;
  }
  if (outcome === "SUPPORT_TICKET") {
    return "This claim is held for review because the refund pattern looks unusual. You will see an update here when Claim Risk decides.";
  }
  if (outcome === "NEED_MORE_INFO") {
    return "A clearer photo or a short extra note is needed before a refund can be decided.";
  }
  if (outcome === "ZONE_BROADCAST") {
    return "This looks like an area-wide delay. Nearby customers were notified; kitchen and rider are not automatically blamed.";
  }
  if (outcome === "NO_ACTION") {
    return "The evidence did not support an automatic refund. You can add more detail if something was missed.";
  }
  return "ResolveX is attaching timing, route, photo, and claim-history evidence to this report.";
}

export default function CustomerApp() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const [orderId, setOrderId] = useState(params.get("order") || "");
  const [type, setType] = useState("late");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [record, setRecord] = useState(null);
  const [orders, setOrders] = useState([]);
  const [merchants, setMerchants] = useState([]);
  const [notices, setNotices] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedIssue = ISSUES.find((issue) => issue.id === type) || ISSUES[0];
  const selectedOrder = orders.find((order) => order.id === orderId);
  const payment = paymentOf(selectedOrder || record?.case);
  const delivery = deliveryOf(selectedOrder);
  const restaurant = useMemo(() => {
    const merchant = merchants.find((row) => row.id === selectedOrder?.merchant_id);
    return merchant ? merchantTitle(merchant.name) : selectedOrder ? "Restaurant" : "";
  }, [merchants, selectedOrder]);

  useEffect(() => {
    api("/commerce/orders").then(setOrders).catch((e) => setError(e.message));
    api("/commerce/catalog").then((catalog) => setMerchants(catalog.merchants || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    const id = new URLSearchParams(location.search).get("case");
    if (!id) return;
    api(`/cases/${id}`)
      .then((r) => {
        setRecord(r);
        setOrderId(r.case.order.id);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [location.search]);

  useEffect(() => {
    setNotices([]);
    if (!isOrderId(orderId)) return;
    let cancelled = false;
    let timer;
    const load = async () => {
      try {
        const rows = await api(`/notifications?order_id=${encodeURIComponent(orderId)}`);
        if (!cancelled) setNotices(rows);
      } catch (err) {
        if (cancelled) return;
        if ([401, 403, 404, 422].includes(err.status)) {
          setError(err.message);
          return;
        }
      }
      if (!cancelled) timer = setTimeout(load, 5000);
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [orderId]);

  const claimable = useMemo(
    () => orders.filter((order) => order.status !== "cancelled"),
    [orders]
  );

  async function upload() {
    if (!file) return null;
    const form = new FormData();
    form.append("file", await preparePhoto(file));
    form.append("kind", "claim");
    const saved = await uploadApi(`/commerce/orders/${orderId}/evidence`, form);
    return saved.path || saved.photo_url;
  }

  async function submit(event, additional = false) {
    event.preventDefault();
    if (!additional && !isOrderId(orderId)) {
      setError("Choose an order from the list, or paste a valid Order ID.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const photo = await upload();
      const r = await api(
        additional ? `/cases/${record.case_id}/evidence` : "/cases",
        additional
          ? { photo_url: photo, description }
          : { order_id: orderId, complaint_type: type, description, photo_url: photo }
      );
      setRecord(r);
      history.replaceState(null, "", `?case=${r.case_id}`);
      setFile(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function pickOrder(id) {
    setOrderId(id);
    setError("");
  }

  const outcome = record ? resolution(record) : null;
  const refund = record?.case?.workflow?.refund;
  const casePayment = record?.case?.payment;

  return (
    <div className="page-shell space-y-6 pb-12">
      <section className="overflow-hidden rounded-[2rem] bg-slate-950 px-6 py-8 text-white sm:px-8">
        <p className="text-[11px] font-black uppercase tracking-[0.22em] text-teal-300">Claim report</p>
        <h1 className="mt-3 max-w-3xl text-3xl font-black tracking-tight sm:text-4xl">
          {record ? "Here is what ResolveX decided." : "Tell us what went wrong. Evidence decides the refund."}
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300">
          {record
            ? nextStepCopy(record)
            : "Pick the order, describe the issue, and attach a photo when it helps. Timing, route, photos, area delays, and your refund pattern are reviewed together."}
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[["1", "Choose the order"], ["2", "Describe the issue"], ["3", "See the decision"]].map(([n, label], index) => (
            <div key={label} className={`rounded-2xl border px-4 py-3 text-sm ${record && index === 2 ? "border-teal-300/40 bg-teal-300/10" : "border-white/10 bg-white/5"}`}>
              <p className="text-[11px] font-black uppercase tracking-[0.16em] text-teal-300">Step {n}</p>
              <p className="mt-1 font-semibold">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {notices.map((n) => (
        <aside key={n.id} className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <p className="font-bold text-amber-950">Delivery disruption in your area</p>
          <p className="mt-1 text-sm text-amber-900">{n.message}</p>
          {n.additional_delay_minutes != null && (
            <p className="mt-1 text-sm text-amber-800">Estimated extra delay: {Math.ceil(n.additional_delay_minutes)} minutes</p>
          )}
        </aside>
      ))}

      {error && (
        <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </p>
      )}

      {!record && (
        <form onSubmit={(e) => submit(e)} className="grid gap-5 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-8">
            <section className="panel p-5 sm:p-6">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="kicker">Order</p>
                  <h2 className="mt-1 text-xl font-black tracking-tight">Which delivery is this about?</h2>
                </div>
                <Link to="/my-orders" className="text-sm font-bold text-teal-700">View my orders</Link>
              </div>

              {claimable.length > 0 ? (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {claimable.slice(0, 8).map((order) => {
                    const active = order.id === orderId;
                    const merchant = merchants.find((row) => row.id === order.merchant_id);
                    return (
                      <button
                        key={order.id}
                        type="button"
                        onClick={() => pickOrder(order.id)}
                        className={`rounded-2xl border p-4 text-left transition ${active ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-bold">{merchant ? merchantTitle(merchant.name) : `Order ${order.id.slice(0, 8).toUpperCase()}`}</p>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${active ? "bg-white/15 text-white" : "bg-slate-100 text-slate-600"}`}>
                            {STATUS[order.status] || order.status}
                          </span>
                        </div>
                        <p className={`mt-1 truncate text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>
                          {order.items.map((item) => `${item.qty}× ${item.name}`).join(", ")}
                        </p>
                        <p className={`mt-2 text-sm font-semibold ${active ? "text-teal-200" : "text-slate-900"}`}>
                          LKR {orderTotal(order).toLocaleString()}
                        </p>
                        {order.case_ids?.length > 0 && (
                          <p className={`mt-1 text-[11px] font-semibold ${active ? "text-amber-200" : "text-amber-700"}`}>Claim already filed</p>
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">
                  <p className="font-semibold text-slate-900">No orders to report yet.</p>
                  <p className="mt-1">Place an order first, then come back if something goes wrong.</p>
                  <Link to="/" className="btn mt-3">Order food</Link>
                </div>
              )}

              <label className="mt-4 block text-xs font-semibold text-slate-500">
                Or paste an Order ID
                <input
                  aria-label="Order ID"
                  maxLength={36}
                  pattern={ORDER_ID_PATTERN}
                  className="field mt-1"
                  value={orderId}
                  placeholder="123e4567-e89b-12d3-a456-426614174000"
                  onChange={(e) => pickOrder(e.target.value.trim())}
                />
              </label>
            </section>

            <section className="panel p-5 sm:p-6">
              <p className="kicker">Issue</p>
              <h2 className="mt-1 text-xl font-black tracking-tight">What happened?</h2>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {ISSUES.map((issue) => {
                  const active = type === issue.id;
                  return (
                    <button
                      key={issue.id}
                      type="button"
                      onClick={() => setType(issue.id)}
                      className={`rounded-2xl border p-4 text-left transition ${active ? "border-teal-600 bg-teal-50 ring-2 ring-teal-100" : "border-slate-200 bg-white hover:border-slate-300"}`}
                    >
                      <p className="text-lg">{issue.icon} <span className="font-bold text-slate-950">{issue.label}</span></p>
                      <p className="mt-1 text-xs leading-relaxed text-slate-500">{issue.hint}</p>
                      <p className={`mt-2 text-[11px] font-bold uppercase tracking-wide ${issue.photo ? "text-amber-700" : "text-slate-400"}`}>
                        {issue.photo ? "Photo required" : "Photo optional"}
                      </p>
                    </button>
                  );
                })}
              </div>

              <label className="mt-5 block text-sm font-semibold text-slate-700">
                Extra detail
                <textarea
                  className="field min-h-28"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What should have arrived, what you received, and when you noticed it."
                />
              </label>
            </section>

            <section className="panel p-5 sm:p-6">
              <p className="kicker">Evidence</p>
              <h2 className="mt-1 text-xl font-black tracking-tight">{selectedIssue.photo ? "Add a claim photo" : "Add a photo if you have one"}</h2>
              <p className="mt-1 text-sm text-slate-500">{selectedIssue.photoHint}</p>
              <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center transition hover:border-teal-400 hover:bg-teal-50/40">
                <p className="text-2xl">{preview ? "🖼️" : "📷"}</p>
                <p className="mt-2 text-sm font-bold text-slate-900">{preview ? "Replace photo" : "Take or upload a photo"}</p>
                <p className="mt-1 text-xs text-slate-500">JPEG, PNG, or WebP · used only for this claim</p>
                <input
                  className="sr-only"
                  required={selectedIssue.photo}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
              {preview && <img src={preview} alt="Evidence preview" className="mt-4 max-h-64 w-full rounded-2xl object-cover ring-1 ring-slate-200" />}
            </section>
          </div>

          <aside className="space-y-5 lg:col-span-4">
            <section className="panel overflow-hidden">
              <div className="bg-slate-950 px-5 py-4 text-white">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-teal-300">This report</p>
                <h3 className="mt-1 text-lg font-black">{restaurant || "Select an order"}</h3>
              </div>
              <div className="space-y-4 p-5 text-sm">
                {selectedOrder ? (
                  <>
                    <p className="font-semibold text-slate-900">Order {selectedOrder.id.slice(0, 8).toUpperCase()}</p>
                    <p className="text-slate-500">{new Date(selectedOrder.placed_at).toLocaleString()} · {STATUS[selectedOrder.status]}</p>
                    <ul className="divide-y rounded-2xl bg-slate-50 px-3">
                      {selectedOrder.items.map((item, index) => (
                        <li key={index} className="flex justify-between py-2">
                          <span>{item.qty} × {item.name}</span>
                          <span>LKR {(item.qty * item.price).toLocaleString()}</span>
                        </li>
                      ))}
                      <li className="flex justify-between py-2 font-bold">
                        <span>Paid</span>
                        <span>LKR {orderTotal(selectedOrder).toLocaleString()}</span>
                      </li>
                    </ul>
                    {payment?.status === "captured" && (
                      <p className="rounded-xl bg-teal-50 px-3 py-2 text-xs text-teal-900">
                        Refunds go back to {payment.account || "your ResolveX Pay card"}.
                      </p>
                    )}
                    {delivery?.address && <p className="text-xs text-slate-500">Delivered toward {delivery.address}</p>}
                    {selectedOrder.evidence?.packing && <p className="text-xs text-slate-500">Kitchen packing photo is already on this order.</p>}
                    {selectedOrder.evidence?.handover && <p className="text-xs text-slate-500">Rider handover photo is already on this order.</p>}
                    {selectedOrder.case_ids?.length > 0 && (
                      <Link to={`/report?case=${selectedOrder.case_ids[0]}`} className="btn-secondary w-full text-center">
                        View existing claim
                      </Link>
                    )}
                  </>
                ) : (
                  <p className="text-slate-500">Choose an order to see restaurant, items, and the refund account.</p>
                )}
                <button className="btn w-full py-3" disabled={busy || !orderId}>
                  {busy ? "Analyzing evidence…" : "Submit claim report"}
                </button>
              </div>
            </section>

            <section className="panel p-5">
              <h3 className="font-black text-slate-950">What we check</h3>
              <ul className="mt-3 space-y-3">
                {CHECKS.map(([icon, title, text]) => (
                  <li key={title} className="flex gap-3 text-sm">
                    <span className="text-lg">{icon}</span>
                    <span><b className="text-slate-900">{title}.</b> <span className="text-slate-500">{text}</span></span>
                  </li>
                ))}
              </ul>
            </section>
          </aside>
        </form>
      )}

      {record && (
        <div className="grid gap-5 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-8">
            <section className="panel overflow-hidden">
              <div className="bg-slate-950 px-5 py-5 text-white sm:px-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-black uppercase tracking-[0.18em] text-teal-300">Decision</p>
                    <h2 className="mt-2 text-3xl font-black tracking-tight">{actionLabel(outcome)}</h2>
                    <p className="mt-2 max-w-xl text-sm text-slate-300">{nextStepCopy(record)}</p>
                  </div>
                  <OutcomeBadge outcome={outcome} large />
                </div>
                {refund && (
                  <div className="mt-4 rounded-2xl bg-emerald-400/15 px-4 py-3 text-emerald-50">
                    <p className="text-lg font-black">LKR {Number(refund.amount).toLocaleString()} refunded</p>
                    <p className="mt-1 text-sm text-emerald-100">
                      {refund.reference} · {refund.destination || refund.account || "ResolveX Pay"}
                    </p>
                  </div>
                )}
              </div>
              <div className="grid gap-3 p-5 sm:grid-cols-3">
                <div className="rounded-2xl bg-slate-50 p-3">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Case</p>
                  <p className="mt-1 font-bold">{record.case_id?.slice(0, 8).toUpperCase()}</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Order</p>
                  <p className="mt-1 font-bold">{record.case.order.id.slice(0, 8).toUpperCase()}</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Paid with</p>
                  <p className="mt-1 font-bold">{casePayment?.account || payment?.account || "ResolveX Pay"}</p>
                </div>
              </div>
            </section>

            {outcome === "NEED_MORE_INFO" && (
              <form onSubmit={(e) => submit(e, true)} className="panel space-y-4 p-5 sm:p-6">
                <p className="kicker">More evidence</p>
                <h3 className="text-xl font-black">Add what was requested</h3>
                <p className="text-sm text-slate-600">{record.case.workflow.evidence_request}</p>
                <label className="flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 py-6 text-sm font-semibold">
                  {preview ? "Replace photo" : "Upload another photo"}
                  <input
                    aria-label="Additional evidence"
                    className="sr-only"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    required={record.verdict?.claim_assessment?.photo_required}
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                {preview && <img src={preview} alt="Additional evidence preview" className="max-h-48 rounded-2xl object-cover" />}
                <textarea
                  aria-label="Additional explanation"
                  className="field min-h-24"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Anything else the photo does not show."
                />
                <button className="btn" disabled={busy}>{busy ? "Re-analyzing…" : "Upload and re-analyze"}</button>
              </form>
            )}

            <section className="panel p-5 sm:p-6">
              <p className="kicker">Evidence used</p>
              <h3 className="mt-1 text-xl font-black">How this was decided</h3>
              <div className="mt-4">
                <CasePanel record={record} hideDecision />
              </div>
            </section>
          </div>

          <aside className="space-y-5 lg:col-span-4">
            <section className="panel p-5">
              <h3 className="font-black">Order snapshot</h3>
              <p className="mt-2 text-sm text-slate-500">{record.case.merchant?.name ? merchantTitle(record.case.merchant.name) : "Restaurant"}</p>
              <ul className="mt-3 divide-y rounded-2xl bg-slate-50 px-3 text-sm">
                {(record.case.order.items || []).map((item, index) => (
                  <li key={index} className="flex justify-between py-2">
                    <span>{item.qty} × {item.name}</span>
                    <span>LKR {(item.qty * item.price).toLocaleString()}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">
                Delivered toward {record.case.customer?.address || "your saved address"}.
              </p>
            </section>
            <div className="flex flex-col gap-2">
              <Link to="/my-orders" className="btn text-center">Back to my orders</Link>
              <button
                className="btn-secondary"
                onClick={() => {
                  setRecord(null);
                  setDescription("");
                  history.replaceState(null, "", "/report");
                }}
              >
                Report another order
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, uploadApi } from "../lib/api";
import { preparePhoto } from "../lib/photo";

const STATUS = {
  placed: { label: "Needs approval", tone: "bg-amber-50 text-amber-900 ring-amber-200" },
  preparing: { label: "Preparing", tone: "bg-sky-50 text-sky-800 ring-sky-200" },
  ready: { label: "Packed", tone: "bg-teal-50 text-teal-800 ring-teal-200" },
  picked_up: { label: "With rider", tone: "bg-indigo-50 text-indigo-800 ring-indigo-200" },
  dropped_off: { label: "Delivered", tone: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  completed: { label: "Completed", tone: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  cancelled: { label: "Declined", tone: "bg-rose-50 text-rose-800 ring-rose-200" },
};

const STEPS = [
  ["prep_started_at", "Accepted"],
  ["ready_at", "Packed"],
  ["picked_up_at", "Picked up"],
  ["dropped_off_at", "Delivered"],
];

const COPY = {
  merchant: { kicker: "Kitchen", title: "Restaurant orders", subtitle: "Prepare orders. A nearby rider is assigned automatically when food is packed." },
  rider: { kicker: "Rider", title: "My deliveries", subtitle: "Accept or reject a new assignment, then navigate to the customer and confirm delivery." },
  customer: { kicker: "Customer", title: "My orders", subtitle: "Track a live order or report a problem." },
};

function needsAction(order, mode) {
  if (mode === "merchant") return ["placed", "preparing", "ready"].includes(order.status);
  if (mode === "rider") return ["ready", "picked_up"].includes(order.status);
  return !["dropped_off", "completed", "cancelled"].includes(order.status);
}

function isDone(order) {
  return ["dropped_off", "completed", "cancelled"].includes(order.status);
}

function orderTotal(order) {
  return order.items.reduce((sum, item) => sum + item.qty * item.price, 0);
}

function StatusBadge({ status }) {
  const meta = STATUS[status] ?? { label: status, tone: "bg-slate-100 text-slate-700 ring-slate-200" };
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${meta.tone}`}>{meta.label}</span>;
}

function EvidenceSlot({ label, hint, kind, capture, photo, disabled, onUploaded }) {
  const [busy, setBusy] = useState(false);
  async function choose(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      await onUploaded(kind, file);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm text-slate-600">{hint}</p>
      {photo?.signed_url && (
        <img src={photo.signed_url} alt={label} className="mt-3 max-h-40 w-full rounded-xl object-cover" />
      )}
      <label className="btn-secondary mt-3 inline-flex cursor-pointer">
        {busy ? "Uploading…" : photo ? "Replace photo" : "Take or upload photo"}
        <input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" capture={capture} disabled={disabled || busy} onChange={choose} />
      </label>
    </div>
  );
}

export default function OrderDashboard({ mode = "customer" }) {
  const [orders, setOrders] = useState([]);
  const [riders, setRiders] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [locationState, setLocationState] = useState(mode === "rider" ? "starting" : "off");
  const [currentPosition, setCurrentPosition] = useState(null);
  const [filter, setFilter] = useState(mode === "rider" ? "action" : mode === "merchant" ? "action" : "active");

  const copy = COPY[mode] ?? COPY.customer;
  const load = () => api("/commerce/orders").then(setOrders).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    if (mode === "merchant") api("/commerce/riders").then(setRiders).catch(() => {});
    setFilter(mode === "rider" ? "action" : mode === "merchant" ? "action" : "active");
    return () => clearInterval(timer);
  }, [mode]);

  useEffect(() => {
    if (mode !== "rider") return;
    if (!navigator.geolocation) {
      setLocationState("unsupported");
      setError("Location is not supported in this browser.");
      return;
    }

    let pending = false;
    const watchId = navigator.geolocation.watchPosition(
      async (position) => {
        const payload = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          speed_kmh: Math.max(0, (position.coords.speed || 0) * 3.6),
        };
        setCurrentPosition(payload);
        setLocationState("on");
        if (pending) return;
        pending = true;
        try {
          await api("/commerce/rider/location", payload);
          const active = orders.filter((order) => order.status === "picked_up");
          await Promise.all(active.map((order) => api(`/commerce/orders/${order.id}/position`, payload)));
        } catch (e) {
          setError(e.message);
        } finally {
          pending = false;
        }
      },
      (geoError) => {
        setLocationState("denied");
        setError(`Location access is needed for nearby assignment and live delivery: ${geoError.message}`);
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [mode, orders]);

  const counts = useMemo(() => ({
    action: orders.filter((o) => needsAction(o, mode)).length,
    active: orders.filter((o) => !isDone(o)).length,
    done: orders.filter(isDone).length,
    all: orders.length,
  }), [orders, mode]);

  const filtered = useMemo(() => orders.filter((o) => {
    if (filter === "action") return needsAction(o, mode);
    if (filter === "active") return !isDone(o);
    if (filter === "done") return isDone(o);
    return true;
  }), [orders, filter, mode]);

  useEffect(() => {
    if (!filtered.length) return;
    if (!filtered.some((o) => o.id === selectedId)) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const selected = filtered.find((o) => o.id === selectedId) || filtered[0];
  const delivery = selected?.items?.[0]?.delivery;
  const payment = selected?.items?.[0]?.payment;
  const assignedRider = riders.find((r) => r.id === selected?.rider_id);
  const evidence = selected?.evidence || {};

  async function uploadEvidence(order, kind, file) {
    setError("");
    const form = new FormData();
    form.append("file", await preparePhoto(file));
    form.append("kind", kind);
    try {
      const saved = await uploadApi(`/commerce/orders/${order.id}/evidence`, form);
      setOrders((current) => current.map((row) => (row.id === order.id ? { ...row, evidence: saved.evidence || { ...row.evidence, [kind]: saved } } : row)));
      setNotice(`${kind === "packing" ? "Packing" : "Handover"} photo saved.`);
    } catch (e) {
      setError(e.message);
      throw e;
    }
  }

  async function act(order, action) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      let location = {};
      if (action === "deliver") {
        if (currentPosition) {
          location = { lat: currentPosition.lat, lng: currentPosition.lng };
        } else {
          location = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
            (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
            () => reject(new Error("Allow location access to confirm delivery.")),
            { enableHighAccuracy: true }
          ));
        }
      }

      const result = await api(`/commerce/orders/${order.id}/stage`, { action, ...location });
      if (action === "pack") {
        setNotice(result.rider_id ? "Packed and offered to the nearest available rider." : "Packed. Waiting for an available rider in this zone.");
      }
      if (action === "accept_delivery") {
        setNotice("Assignment accepted. Collect the order from the restaurant.");
      }
      if (action === "decline_delivery") {
        setNotice(result.assignment_pending ? "Assignment declined. No other rider is free yet, so it will be offered again automatically." : "Assignment declined and offered to another nearby rider.");
      }
      await load();
      if (mode === "merchant") api("/commerce/riders").then(setRiders).catch(() => {});
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const filters = mode === "customer"
    ? [{ id: "active", label: "In progress" }, { id: "done", label: "Done" }, { id: "all", label: "All" }]
    : [{ id: "action", label: "Needs action" }, { id: "active", label: "In progress" }, { id: "done", label: "Done" }, { id: "all", label: "All" }];

  return (
    <div className="mx-auto flex max-w-7xl flex-col px-4 py-4 sm:px-6 lg:h-[calc(100vh-3.6rem)]">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">{copy.kicker}</p>
          <h1 className="text-2xl font-bold tracking-tight">{copy.title}</h1>
          <p className="mt-1 text-sm text-slate-500">{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === "rider" && (
            <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${locationState === "on" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
              {locationState === "on" ? "● Location active" : "Location required"}
            </span>
          )}
          {mode === "customer" && <Link to="/" className="btn">Order again</Link>}
          {mode === "merchant" && <Link to="/partner" className="btn-secondary">Claims</Link>}
        </div>
      </div>

      <div className="mb-3 flex w-fit flex-wrap gap-1 rounded-full bg-slate-100 p-1">
        {filters.map((f) => (
          <button key={f.id} type="button" onClick={() => setFilter(f.id)} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${filter === f.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
            {f.label} {counts[f.id] ?? 0}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {notice && <p className="mb-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      {!orders.length && <div className="panel p-8 text-sm text-slate-500">No orders yet. New assignments appear here automatically.</div>}

      {!!orders.length && (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12">
          <aside className="min-h-0 space-y-2 lg:col-span-4 lg:overflow-y-auto lg:pr-1">
            {filtered.map((o) => (
              <button key={o.id} type="button" onClick={() => setSelectedId(o.id)} className={`w-full rounded-2xl border bg-white p-4 text-left shadow-sm transition ${selectedId === o.id ? "border-slate-900 ring-2 ring-slate-900/10" : "border-slate-200 hover:border-slate-300"}`}>
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold">Order {o.id.slice(0, 8).toUpperCase()}</p>
                  <StatusBadge status={o.status} />
                </div>
                <p className="mt-1 truncate text-xs text-slate-500">{o.items.map((item) => `${item.qty}× ${item.name}`).join(", ")}</p>
                <p className="mt-2 text-sm font-medium">LKR {orderTotal(o).toLocaleString()}</p>
              </button>
            ))}
            {!filtered.length && <p className="p-6 text-center text-sm text-slate-500">Nothing in this filter.</p>}
          </aside>

          <article className="panel min-h-0 lg:col-span-8 lg:overflow-y-auto">
            {selected ? (
              <>
                <div className="bg-slate-900 px-5 py-4 text-white">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <h2 className="text-2xl font-bold">{selected.id.slice(0, 8).toUpperCase()}</h2>
                    <StatusBadge status={selected.status} />
                  </div>
                  <p className="mt-2 text-sm text-slate-300">{new Date(selected.placed_at).toLocaleString()} · ETA {selected.promised_delivery_minutes} min{selected.is_late_flagged ? " · Late" : ""}</p>
                </div>

                <div className="space-y-5 p-5">
                  <ol className="grid grid-cols-4 gap-2 text-center text-[11px]">
                    {STEPS.map(([key, label]) => (
                      <li key={key} className={selected[key] ? "font-semibold text-teal-800" : "text-slate-400"}>
                        <span className={`mx-auto mb-1 block h-2 w-2 rounded-full ${selected[key] ? "bg-teal-600" : "bg-slate-200"}`} />
                        {label}
                        <span className="mt-0.5 block text-[10px]">{selected[key] ? new Date(selected[key]).toLocaleTimeString() : "pending"}</span>
                      </li>
                    ))}
                  </ol>

                  <ul className="divide-y rounded-2xl bg-slate-50 px-4">
                    {selected.items.map((item, i) => <li key={i} className="flex justify-between py-2 text-sm"><span>{item.qty} × {item.name}</span><span>LKR {(item.qty * item.price).toLocaleString()}</span></li>)}
                    <li className="flex justify-between py-2 text-sm font-bold"><span>Total</span><span>LKR {orderTotal(selected).toLocaleString()}</span></li>
                  </ul>

                  {payment?.status === "captured" && (
                    <div className="rounded-2xl border border-teal-100 bg-teal-50/60 p-4 text-sm">
                      <p className="text-[11px] uppercase tracking-wide text-teal-800">ResolveX Pay</p>
                      <p className="mt-1 font-semibold text-slate-950">Paid · {payment.account || `${payment.brand || "Card"} ••${payment.last4 || "••••"}`}</p>
                      <p className="mt-1 text-xs text-slate-500">Refunds from claims go back to this account.</p>
                    </div>
                  )}
                  {payment?.status === "pending" && mode === "customer" && (
                    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">
                      <p className="font-semibold text-amber-950">Payment pending</p>
                      <p className="mt-1 text-amber-800">Pay on the ResolveX Pay gateway to send this order to the kitchen.</p>
                      <Link to={`/pay/${selected.id}`} className="btn mt-3">Open payment gateway</Link>
                    </div>
                  )}
                  {payment?.status === "pending" && mode === "merchant" && (
                    <p className="rounded-2xl bg-amber-50 p-3 text-sm text-amber-800">Waiting for the customer to pay on ResolveX Pay.</p>
                  )}

                  {delivery && (
                    <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500">Customer details</p>
                      <p className="mt-1 font-semibold">{delivery.address}</p>
                      <a className="mt-1 block text-teal-800" href={`tel:${delivery.phone}`}>{delivery.phone}</a>
                      {delivery.instructions && <p className="mt-2 text-slate-600">{delivery.instructions}</p>}
                      {mode === "rider" && (
                        <a target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-xl bg-slate-950 px-3 py-2 font-semibold text-white" href={`https://www.google.com/maps/dir/?api=1&destination=${delivery.lat},${delivery.lng}`}>
                          Get directions
                        </a>
                      )}
                    </div>
                  )}

                  {mode === "customer" && (
                    <div className="flex flex-wrap gap-2">
                      <Link to={`/report?order=${selected.id}`} className="btn-secondary">Report a problem</Link>
                      {selected.case_ids?.map((id) => <Link key={id} className="btn-secondary" to={`/report?case=${id}`}>View claim {id.slice(0, 6)}</Link>)}
                    </div>
                  )}

                  {mode === "merchant" && selected.status === "placed" && (
                    <div className="flex flex-wrap gap-2">
                      <button className="btn" disabled={busy || payment?.status !== "captured"} onClick={() => act(selected, "accept")}>Approve & prepare</button>
                      <button className="btn-secondary" disabled={busy} onClick={() => act(selected, "reject")}>Decline order</button>
                    </div>
                  )}

                  {mode === "merchant" && selected.status === "preparing" && (
                    <div className="space-y-3">
                      <EvidenceSlot
                        label="Packing photo"
                        hint="Required before the order can be marked packed."
                        kind="packing"
                        capture="environment"
                        photo={evidence.packing}
                        disabled={busy}
                        onUploaded={(kind, file) => uploadEvidence(selected, kind, file)}
                      />
                      <button className="btn" disabled={busy || !evidence.packing} onClick={() => act(selected, "pack")}>
                        Mark packed & auto-assign rider
                      </button>
                    </div>
                  )}

                  {mode === "merchant" && selected.status === "ready" && (
                    <div className="space-y-3">
                      {evidence.packing?.signed_url && (
                        <img src={evidence.packing.signed_url} alt="Packing photo" className="max-h-40 w-full rounded-2xl object-cover" />
                      )}
                      <div className="rounded-2xl border border-slate-200 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Assigned rider</p>
                      <p className="mt-1 font-semibold">{assignedRider?.name || (selected.rider_id ? "Assigned rider" : "Looking for a rider")}</p>
                      {assignedRider && <p className="text-sm capitalize text-slate-500">{assignedRider.vehicle} · {assignedRider.zone_id}</p>}
                      <p className="mt-2 text-sm text-slate-500">
                        {!selected.rider_id
                          ? "No rider is free in this zone yet. The order is offered again automatically."
                          : selected.rider_accepted_at
                            ? `Accepted at ${new Date(selected.rider_accepted_at).toLocaleTimeString()}. Hand the order over when they arrive.`
                            : "Offered. Waiting for the rider to accept, then it passes to the next rider automatically."}
                      </p>
                      <button className="btn mt-3" disabled={busy || !selected.rider_accepted_at} onClick={() => act(selected, "handover")}>Hand over order</button>
                    </div>
                    </div>
                  )}

                  {mode === "rider" && selected.status === "ready" && (
                    <div className="space-y-3">
                      {selected.rider_accepted_at ? (
                        <p className="rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-800">
                          Accepted at {new Date(selected.rider_accepted_at).toLocaleTimeString()}. Collect the order — the restaurant confirms the handover.
                        </p>
                      ) : (
                        <p className="rounded-2xl bg-amber-50 p-3 text-sm text-amber-800">
                          New assignment. Accept it to collect this order, or reject it to pass it to another nearby rider.
                        </p>
                      )}
                      <div className="flex flex-wrap gap-2">
                        {!selected.rider_accepted_at && (
                          <button className="btn" disabled={busy} onClick={() => act(selected, "accept_delivery")}>Accept assignment</button>
                        )}
                        <button className="btn-danger" disabled={busy} onClick={() => act(selected, "decline_delivery")}>Reject assignment</button>
                      </div>
                    </div>
                  )}

                  {mode === "rider" && selected.status === "picked_up" && (
                    <div className="space-y-3">
                      <EvidenceSlot
                        label="Handover photo"
                        hint="Take a photo of the sealed order before confirming delivery."
                        kind="handover"
                        capture="environment"
                        photo={evidence.handover}
                        disabled={busy}
                        onUploaded={(kind, file) => uploadEvidence(selected, kind, file)}
                      />
                      <button disabled={busy || !evidence.handover} className="btn" onClick={() => act(selected, "deliver")}>Confirm delivery</button>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="grid h-full place-items-center p-8 text-sm text-slate-500">Select an order.</p>
            )}
          </article>
        </div>
      )}
    </div>
  );
}

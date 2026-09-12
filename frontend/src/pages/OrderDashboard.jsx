import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

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
  merchant: {
    kicker: "Kitchen",
    title: "Restaurant orders",
    subtitle: "Approve, pack, and hand over from one order at a time.",
  },
  rider: {
    kicker: "On the road",
    title: "Deliveries",
    subtitle: "Open a drop-off, share location, and confirm when it is done.",
  },
  customer: {
    kicker: "Customer",
    title: "My orders",
    subtitle: "Track a live order or report a problem from the detail panel.",
  },
};

function needsAction(order, mode) {
  if (mode === "merchant") return ["placed", "preparing", "ready"].includes(order.status);
  if (mode === "rider") return order.status === "picked_up";
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

export default function OrderDashboard({ mode = "customer" }) {
  const [orders, setOrders] = useState([]);
  const [riders, setRiders] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [riderByOrder, setRiderByOrder] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tracking, setTracking] = useState(null);
  const [filter, setFilter] = useState(mode === "rider" ? "active" : mode === "merchant" ? "action" : "active");

  const copy = COPY[mode] ?? COPY.customer;

  const load = () => api("/commerce/orders").then(setOrders).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    if (mode === "merchant") api("/commerce/riders").then(setRiders).catch((e) => setError(e.message));
    setFilter(mode === "rider" ? "active" : mode === "merchant" ? "action" : "active");
    return () => clearInterval(timer);
  }, [mode]);

  useEffect(() => {
    if (mode !== "rider" || !orders.length) return;
    const actionCount = orders.filter((o) => needsAction(o, "rider")).length;
    const activeCount = orders.filter((o) => !isDone(o)).length;
    setFilter((current) => {
      if (current === "action" && actionCount === 0) return activeCount ? "active" : "all";
      if (current === "active" && activeCount === 0) return "all";
      return current;
    });
  }, [mode, orders]);

  useEffect(() => {
    if (!tracking) return;
    let pending = false;
    const id = navigator.geolocation.watchPosition(
      async (p) => {
        if (pending) return;
        pending = true;
        try {
          await api(`/commerce/orders/${tracking}/position`, {
            lat: p.coords.latitude,
            lng: p.coords.longitude,
            speed_kmh: Math.max(0, (p.coords.speed || 0) * 3.6),
          });
        } catch (e) {
          setError(e.message);
          setTracking(null);
        } finally {
          pending = false;
        }
      },
      (e) => {
        setError(e.message);
        setTracking(null);
      },
      { enableHighAccuracy: true, maximumAge: 10000 }
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [tracking]);

  const counts = useMemo(
    () => ({
      action: orders.filter((o) => needsAction(o, mode)).length,
      active: orders.filter((o) => !isDone(o)).length,
      done: orders.filter(isDone).length,
      all: orders.length,
    }),
    [orders, mode]
  );

  const filtered = useMemo(() => {
    return orders.filter((o) => {
      if (filter === "action") return needsAction(o, mode);
      if (filter === "active") return !isDone(o);
      if (filter === "done") return isDone(o);
      return true;
    });
  }, [orders, filter, mode]);

  useEffect(() => {
    if (!filtered.length) return;
    if (!filtered.some((o) => o.id === selectedId)) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const selected = filtered.find((o) => o.id === selectedId) || filtered[0];
  const delivery = selected?.items[0]?.delivery;
  const assignedRider = riders.find((r) => r.id === (riderByOrder[selected?.id] || selected?.rider_id));

  async function act(order, action) {
    setBusy(true);
    setError("");
    try {
      let location = {};
      if (action === "deliver") {
        location = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(
            (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
            () => reject(new Error("Allow location access to record delivery.")),
            { enableHighAccuracy: true }
          )
        );
      }
      await api(`/commerce/orders/${order.id}/stage`, {
        action,
        ...location,
        ...(action === "handover" ? { rider_id: riderByOrder[order.id] } : {}),
      });
      if (action === "deliver") setTracking(null);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const filters =
    mode === "customer"
      ? [
          { id: "active", label: "In progress" },
          { id: "done", label: "Done" },
          { id: "all", label: "All" },
        ]
      : [
          { id: "action", label: "Needs action" },
          { id: "active", label: "In progress" },
          { id: "done", label: "Done" },
          { id: "all", label: "All" },
        ];

  return (
    <div className="mx-auto flex max-w-7xl flex-col px-4 py-4 sm:px-6 lg:h-[calc(100vh-3.6rem)]">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">{copy.kicker}</p>
          <h1 className="text-2xl font-bold tracking-tight">{copy.title}</h1>
          <p className="mt-1 text-sm text-slate-500">{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === "customer" && (
            <Link to="/" className="btn">
              Order again
            </Link>
          )}
          {mode === "merchant" && (
            <Link to="/partner" className="btn-secondary">
              Claims & disputes
            </Link>
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1 rounded-full bg-slate-100 p-1 w-fit">
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
              filter === f.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
            }`}
          >
            {f.label} {counts[f.id] ?? 0}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {!orders.length && <div className="panel p-8 text-sm text-slate-500">No orders yet. New orders appear here automatically.</div>}

      {!!orders.length && (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12">
          <aside className="min-h-0 space-y-2 lg:col-span-4 lg:overflow-y-auto lg:pr-1">
            {filtered.map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => setSelectedId(o.id)}
                className={`w-full rounded-2xl border bg-white p-4 text-left shadow-sm transition ${
                  selectedId === o.id ? "border-slate-900 ring-2 ring-slate-900/10" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold">Order {o.id.slice(0, 8).toUpperCase()}</p>
                  <StatusBadge status={o.status} />
                </div>
                <p className="mt-1 truncate text-xs text-slate-500">
                  {o.items.map((item) => `${item.qty}× ${item.name}`).join(", ")}
                </p>
                <p className="mt-2 text-sm font-medium">LKR {orderTotal(o).toLocaleString()}</p>
              </button>
            ))}
            {!filtered.length && <p className="p-6 text-center text-sm text-slate-500">Nothing in this filter.</p>}
          </aside>

          <article className="panel min-h-0 lg:col-span-8 lg:overflow-y-auto">
            {selected ? (
              <>
                <div className="bg-slate-900 px-5 py-4 text-white">
                  <p className="text-xs uppercase tracking-[0.16em] text-teal-200">Selected order</p>
                  <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
                    <h2 className="text-2xl font-bold">{selected.id.slice(0, 8).toUpperCase()}</h2>
                    <StatusBadge status={selected.status} />
                  </div>
                  <p className="mt-2 text-sm text-slate-300">
                    {new Date(selected.placed_at).toLocaleString()} · ETA {selected.promised_delivery_minutes} min
                    {selected.is_late_flagged ? " · Late" : ""}
                  </p>
                </div>

                <div className="space-y-5 p-5">
                  <ol className="grid grid-cols-4 gap-2 text-center text-[11px]">
                    {STEPS.map(([key, label]) => (
                      <li key={key} className={selected[key] ? "font-semibold text-teal-800" : "text-slate-400"}>
                        <span className={`mx-auto mb-1 block h-2 w-2 rounded-full ${selected[key] ? "bg-teal-600" : "bg-slate-200"}`} />
                        {label}
                        <span className="mt-0.5 block text-[10px]">
                          {selected[key] ? new Date(selected[key]).toLocaleTimeString() : "pending"}
                        </span>
                      </li>
                    ))}
                  </ol>

                  <ul className="divide-y rounded-2xl bg-slate-50 px-4">
                    {selected.items.map((item, i) => (
                      <li key={i} className="flex justify-between py-2 text-sm">
                        <span>
                          {item.qty} × {item.name}
                        </span>
                        <span>LKR {(item.qty * item.price).toLocaleString()}</span>
                      </li>
                    ))}
                    <li className="flex justify-between py-2 text-sm font-bold">
                      <span>Total</span>
                      <span>LKR {orderTotal(selected).toLocaleString()}</span>
                    </li>
                  </ul>

                  {delivery && (
                    <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500">Drop-off</p>
                      <p className="mt-1 font-medium">{delivery.address}</p>
                      <p className="text-slate-600">{delivery.phone}</p>
                      {delivery.instructions && <p className="mt-1 text-slate-600">{delivery.instructions}</p>}
                      {mode === "rider" && (
                        <a
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-sm font-medium text-teal-800"
                          href={`https://www.google.com/maps/dir/?api=1&destination=${delivery.lat},${delivery.lng}`}
                        >
                          Open directions
                        </a>
                      )}
                    </div>
                  )}

                  {mode === "customer" && (
                    <div className="flex flex-wrap gap-2">
                      <Link to={`/report?order=${selected.id}`} className="btn-secondary">
                        Report a problem
                      </Link>
                      {selected.case_ids?.map((id) => (
                        <Link key={id} className="btn-secondary" to={`/report?case=${id}`}>
                          View claim {id.slice(0, 6)}
                        </Link>
                      ))}
                    </div>
                  )}

                  {mode === "merchant" && selected.status === "placed" && (
                    <div className="flex flex-wrap gap-2">
                      <button className="btn" disabled={busy} onClick={() => act(selected, "accept")}>
                        Approve & start preparing
                      </button>
                      <button className="btn-secondary" disabled={busy} onClick={() => act(selected, "reject")}>
                        Decline
                      </button>
                    </div>
                  )}

                  {mode === "merchant" && selected.status === "preparing" && (
                    <button className="btn" disabled={busy} onClick={() => act(selected, "pack")}>
                      Mark packed
                    </button>
                  )}

                  {mode === "merchant" && selected.status === "ready" && (
                    <div className="space-y-3">
                      <p className="text-sm font-medium">Assign a rider</p>
                      <div className="grid gap-2 sm:grid-cols-2" role="listbox" aria-label="Assign rider">
                        {riders.map((r) => {
                          const active = (riderByOrder[selected.id] || "") === r.id;
                          return (
                            <button
                              key={r.id}
                              type="button"
                              role="option"
                              aria-selected={active}
                              onClick={() => setRiderByOrder((prev) => ({ ...prev, [selected.id]: r.id }))}
                              className={`rounded-2xl border p-3 text-left text-sm ${
                                active ? "border-slate-900 ring-2 ring-slate-900/10" : "border-slate-200"
                              }`}
                            >
                              <p className="font-semibold">{r.name}</p>
                              <p className="text-xs capitalize text-slate-500">
                                {r.vehicle}
                                {r.zone_id ? ` · ${r.zone_id}` : ""}
                              </p>
                            </button>
                          );
                        })}
                      </div>
                      {!riders.length && <p className="text-sm text-slate-500">No riders yet. An admin can create rider logins.</p>}
                      <button className="btn" disabled={busy || !riderByOrder[selected.id]} onClick={() => act(selected, "handover")}>
                        Hand over to {assignedRider?.name || "rider"}
                      </button>
                    </div>
                  )}

                  {mode === "rider" && selected.status === "picked_up" && (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => {
                          if (!navigator.geolocation) {
                            setError("Location is not supported in this browser.");
                            return;
                          }
                          setTracking(tracking === selected.id ? null : selected.id);
                        }}
                      >
                        {tracking === selected.id ? "Stop sharing location" : "Share live location"}
                      </button>
                      <button disabled={busy} className="btn" onClick={() => act(selected, "deliver")}>
                        Confirm delivery
                      </button>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="grid h-full place-items-center p-8 text-sm text-slate-500">Select an order to work it.</p>
            )}
          </article>
        </div>
      )}
    </div>
  );
}

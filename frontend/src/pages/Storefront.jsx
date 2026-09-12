import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../lib/api";

function merchantParts(name = "") {
  const [title, ...rest] = name.split(" · ");
  return { title: title || "Restaurant", note: rest.join(" · ") };
}

function QtyStepper({ name, count, onChange }) {
  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <button type="button" className="qty-btn" aria-label={`Remove one ${name}`} onClick={() => onChange(-1)}>−</button>
      <span className="inline-block w-5 text-center text-sm font-bold">{count}</span>
      <button type="button" className="qty-btn-dark" aria-label={`Add one ${name}`} onClick={() => onChange(1)}>+</button>
    </div>
  );
}

const FLOW = [
  ["01", "Order", "Choose a kitchen and place a customer order."],
  ["02", "Prepare", "Merchant actions record acceptance, packing, and handover."],
  ["03", "Deliver", "Rider pickup, route points, and drop-off become evidence."],
  ["04", "Resolve", "Claims combine timing, route, zone, photo, and history signals."],
];

const TRUST = [
  ["⚡", "Proactive delay detection", "ResolveX can flag late orders before a customer needs to complain."],
  ["📍", "Route evidence", "GPS points help explain detours, long stops, and final drop-off accuracy."],
  ["🌐", "Zone intelligence", "Area-wide delays are separated from merchant or rider responsibility."],
  ["⚖️", "Fair resolution", "Operational fault and claim-risk screening are kept separate for clearer decisions."],
];

export default function Storefront() {
  const { user, role } = useAuth();
  const navigate = useNavigate();
  const shopRef = useRef(null);
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [zone, setZone] = useState("all");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [basket, setBasket] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("resolvex-basket")) || { merchant: "", items: {} };
    } catch {
      return { merchant: "", items: {} };
    }
  });
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [instructions, setInstructions] = useState("");
  const [requestId, setRequestId] = useState(null);

  useEffect(() => {
    api("/commerce/catalog").then(setCatalog).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    localStorage.setItem("resolvex-basket", JSON.stringify(basket));
    setRequestId(null);
  }, [basket]);

  const products = catalog?.products ?? [];
  const merchants = catalog?.merchants ?? [];
  const selectedMerchant = merchants.find((m) => m.id === basket.merchant);
  const zones = useMemo(() => {
    const ids = Array.from(new Set(merchants.map((m) => m.zone_id).filter(Boolean))).sort();
    return ["all", ...ids];
  }, [merchants]);
  const filteredMerchants = useMemo(() => {
    const q = query.trim().toLowerCase();
    return merchants.filter((m) => {
      if (zone !== "all" && m.zone_id !== zone) return false;
      if (!q) return true;
      const { title, note } = merchantParts(m.name);
      return `${title} ${note} ${m.zone_id ?? ""}`.toLowerCase().includes(q);
    });
  }, [merchants, query, zone]);
  const showPicker = pickerOpen || !selectedMerchant;
  const categories = useMemo(() => ["all", ...Array.from(new Set(products.map((p) => p.category)))], [products]);
  const visible = products.filter((p) => category === "all" || p.category === category);
  const total = products.reduce((sum, p) => sum + p.price * (basket.items[p.id] || 0), 0);
  const basketItems = products.filter((p) => basket.items[p.id] > 0);
  const basketCount = Object.values(basket.items).reduce((sum, qty) => sum + (qty || 0), 0);

  function quantity(id, change) {
    setBasket((b) => ({
      ...b,
      items: { ...b.items, [id]: Math.max(0, Math.min(20, (b.items[id] || 0) + change)) },
    }));
  }

  function pickMerchant(id) {
    setBasket((b) => (b.merchant === id ? b : { merchant: id, items: {} }));
    setPickerOpen(false);
    setQuery("");
  }

  function locate() {
    if (!navigator.geolocation) {
      setError("Location is unavailable. Enter the coordinates below.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLat(p.coords.latitude.toFixed(6));
        setLng(p.coords.longitude.toFixed(6));
        setError("");
      },
      () => setError("Location permission was not granted. Enter your delivery coordinates below."),
      { enableHighAccuracy: true, maximumAge: 10000 }
    );
  }

  async function place(e) {
    e.preventDefault();
    if (!user) {
      navigate("/login", { state: { from: "/" } });
      return;
    }
    if (role !== "customer") {
      setError("Sign in with a customer account to place an order.");
      return;
    }
    setBusy(true);
    setError("");
    const id = requestId || crypto.randomUUID();
    setRequestId(id);
    try {
      await api("/commerce/orders", {
        request_id: id,
        merchant_id: basket.merchant,
        items: Object.entries(basket.items)
          .filter(([, qty]) => qty > 0)
          .map(([product_id, qty]) => ({ product_id, qty })),
        address,
        phone,
        lat: Number(lat),
        lng: Number(lng),
        instructions,
      });
      setBasket({ merchant: basket.merchant, items: {} });
      navigate("/my-orders");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative overflow-hidden pb-12">
      <section className="page-shell pt-5">
        <div className="relative overflow-hidden rounded-[2rem] bg-slate-950 text-white shadow-[0_35px_110px_-50px_rgba(15,23,42,.95)]">
          <div className="pointer-events-none absolute -right-16 -top-20 h-72 w-72 rounded-full bg-teal-400/20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 left-1/3 h-64 w-64 rounded-full bg-amber-300/10 blur-3xl" />
          <div className="relative grid gap-10 px-6 py-10 sm:px-9 lg:grid-cols-[1.08fr_.92fr] lg:items-center lg:py-14">
            <div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-teal-200">Live evidence</span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-300">Fair claims</span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-300">Real-time delivery</span>
              </div>
              <p className="mt-6 text-xs font-black uppercase tracking-[0.28em] text-teal-300">ResolveX delivery intelligence</p>
              <h1 className="mt-3 max-w-3xl text-4xl font-black leading-[1.02] tracking-tight sm:text-5xl lg:text-6xl">
                Order with confidence. Resolve problems with <span className="text-teal-200">evidence.</span>
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-relaxed text-slate-300">
                From checkout to drop-off, ResolveX keeps the operational story connected. If something goes wrong, the same timestamps, route points, zone conditions, and claim evidence support the decision.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <button className="rounded-2xl bg-teal-300 px-5 py-3 text-sm font-black text-slate-950 shadow-lg transition hover:-translate-y-0.5 hover:bg-teal-200" onClick={() => shopRef.current?.scrollIntoView({ behavior: "smooth" })}>
                  Start ordering →
                </button>
                {!user ? (
                  <Link className="rounded-2xl border border-white/15 bg-white/[0.06] px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10" to="/signup">Create account</Link>
                ) : (
                  <Link className="rounded-2xl border border-white/15 bg-white/[0.06] px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10" to="/my-orders">View my orders</Link>
                )}
              </div>
              <div className="mt-8 grid max-w-2xl grid-cols-3 gap-3">
                {[['5', 'evidence engines'], ['4', 'delivery roles'], ['1', 'shared timeline']].map(([value, label]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 backdrop-blur">
                    <p className="text-2xl font-black">{value}</p>
                    <p className="text-xs text-slate-400">{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="rounded-[1.75rem] border border-white/10 bg-white/[0.06] p-4 backdrop-blur-xl">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.2em] text-teal-300">Live order story</p>
                    <p className="mt-1 text-lg font-bold">From kitchen to resolution</p>
                  </div>
                  <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-xs font-bold text-emerald-200">Connected</span>
                </div>
                <div className="mt-5 space-y-2.5">
                  {FLOW.map(([num, title, text], index) => (
                    <div key={title} className="flex gap-3 rounded-2xl border border-white/10 bg-black/10 p-3.5 transition hover:bg-white/[0.06]">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-300/10 text-xs font-black text-teal-200">{num}</span>
                      <div>
                        <p className="font-bold">{title}</p>
                        <p className="mt-1 text-xs leading-relaxed text-slate-400">{text}</p>
                      </div>
                      <span className={`ml-auto mt-1.5 h-2.5 w-2.5 rounded-full ${index < 3 ? "bg-teal-300" : "bg-amber-300"}`} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="page-shell py-2">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {TRUST.map(([icon, title, text]) => (
            <article key={title} className="metric-card group p-5">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-xl text-white transition group-hover:-translate-y-0.5 group-hover:scale-105">{icon}</span>
              <h2 className="mt-4 font-bold text-slate-950">{title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{text}</p>
            </article>
          ))}
        </div>
      </section>

      {error && (
        <div className="page-shell py-2">
          <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            <p className="font-bold">Something needs attention</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <section ref={shopRef} className="page-shell pt-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="kicker">Order experience</p>
            <h2 className="page-title mt-1">Choose a kitchen, then build your basket.</h2>
            <p className="page-subtitle">Your order starts the same evidence trail used later for tracking and claims.</p>
          </div>
          {user && role === "customer" && <Link to="/my-orders" className="btn-secondary">View active orders</Link>}
        </div>

        <div className="grid gap-5 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-8">
            <section className="panel p-4 sm:p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="kicker">Step 1</p>
                  <h3 className="mt-1 text-xl font-black tracking-tight">Choose a restaurant</h3>
                </div>
                {selectedMerchant && (
                  <button className="text-sm font-bold text-teal-700" onClick={() => setPickerOpen((open) => !open)}>{showPicker ? "Done" : "Change"}</button>
                )}
              </div>

              {selectedMerchant && !showPicker && (
                <div className="mt-4 flex items-center gap-4 rounded-2xl border border-teal-200/70 bg-teal-50/50 p-4">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-xl shadow-sm">🍽️</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-black text-slate-950">{merchantParts(selectedMerchant.name).title}</p>
                    <p className="mt-1 text-xs text-slate-500">{selectedMerchant.avg_prep_minutes} min prep{selectedMerchant.zone_id ? ` · ${selectedMerchant.zone_id}` : ""}</p>
                  </div>
                  <span className="status-pill">Selected</span>
                </div>
              )}

              {showPicker && (
                <div className="mt-4">
                  <input className="field" type="search" placeholder="Search restaurant or zone" value={query} onChange={(e) => setQuery(e.target.value)} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    {zones.map((z) => (
                      <button key={z} type="button" onClick={() => setZone(z)} className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${zone === z ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                        {z === "all" ? "All zones" : z}
                      </button>
                    ))}
                  </div>
                  <div className="scroll-pane mt-3 grid max-h-64 gap-2 sm:grid-cols-2">
                    {filteredMerchants.map((m) => {
                      const active = basket.merchant === m.id;
                      return (
                        <button key={m.id} type="button" onClick={() => pickMerchant(m.id)} className={`rounded-2xl border p-3 text-left transition ${active ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-sm"}`}>
                          <p className="font-bold">{merchantParts(m.name).title}</p>
                          <p className={`mt-1 text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>{m.avg_prep_minutes} min prep{m.zone_id ? ` · ${m.zone_id}` : ""}</p>
                        </button>
                      );
                    })}
                    {catalog && !filteredMerchants.length && <p className="col-span-full py-6 text-center text-sm text-slate-500">No restaurants match your search.</p>}
                  </div>
                </div>
              )}
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="kicker">Step 2</p>
                  <h3 className="mt-1 text-xl font-black tracking-tight">Build your basket</h3>
                </div>
                <div className="flex flex-wrap gap-1 rounded-full bg-slate-100 p-1">
                  {categories.map((c) => (
                    <button key={c} type="button" onClick={() => setCategory(c)} className={`rounded-full px-3 py-1.5 text-xs font-bold capitalize transition ${category === c ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-900"}`}>
                      {c === "all" ? "All" : c}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {visible.map((p) => (
                  <article key={p.id} className="group rounded-2xl border border-slate-200/80 bg-white p-4 transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md">
                    <div className="flex gap-3">
                      <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-50 to-amber-50 text-3xl">{p.emoji}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-teal-700">{p.category}</p>
                        <h4 className="mt-1 font-bold text-slate-950">{p.name}</h4>
                        <p className="mt-1 text-sm font-semibold text-slate-600">LKR {p.price.toLocaleString()}</p>
                      </div>
                    </div>
                    <div className="mt-4 flex items-center justify-between">
                      <span className="text-xs text-slate-400">Prepared after order</span>
                      {basket.items[p.id] > 0 ? (
                        <QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} />
                      ) : (
                        <button type="button" className="btn py-1.5" disabled={!basket.merchant} onClick={() => quantity(p.id, 1)}>Add</button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
              {!basket.merchant && catalog && <p className="mt-4 rounded-2xl bg-amber-50 p-3 text-sm text-amber-800">Choose a restaurant first to add menu items.</p>}
            </section>
          </div>

          <aside className="panel h-fit overflow-hidden lg:sticky lg:top-24 lg:col-span-4">
            <div className="bg-slate-950 px-5 py-4 text-white">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-teal-300">Step 3</p>
                  <h3 className="mt-1 text-xl font-black">Checkout</h3>
                </div>
                <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-slate-200">{basketCount} item{basketCount === 1 ? "" : "s"}</span>
              </div>
            </div>

            <div className="p-5">
              {!total && <div className="rounded-2xl bg-slate-50 p-5 text-center"><p className="text-2xl">🧺</p><p className="mt-2 text-sm font-bold text-slate-700">Your basket is empty</p><p className="mt-1 text-xs text-slate-500">Choose a restaurant and add a dish to continue.</p></div>}

              <div className="divide-y divide-slate-100">
                {basketItems.map((p) => (
                  <div key={p.id} className="py-3">
                    <div className="flex items-start justify-between gap-3"><p className="text-sm font-bold">{p.name}</p><span className="text-sm font-semibold">LKR {(p.price * basket.items[p.id]).toLocaleString()}</span></div>
                    <div className="mt-2"><QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} /></div>
                  </div>
                ))}
              </div>

              <div className="mt-2 flex items-center justify-between border-t border-slate-200 pt-4 text-base font-black"><span>Total</span><span>LKR {total.toLocaleString()}</span></div>

              {total > 0 && (
                <form onSubmit={place} className="mt-5 space-y-3">
                  <div className="flex items-center justify-between"><p className="text-sm font-black">Delivery details</p><span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Saved to order evidence</span></div>
                  <label className="block text-sm font-semibold text-slate-700">Street address<textarea required minLength={8} className="field" rows={2} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="House / street / landmark" /></label>
                  <label className="block text-sm font-semibold text-slate-700">Contact number<input required minLength={7} className="field" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="07X XXX XXXX" /></label>
                  <div className="flex items-center justify-between gap-2 rounded-2xl bg-slate-50 p-3">
                    <div><p className="text-xs font-bold text-slate-700">Delivery pin</p><p className="text-[11px] text-slate-500">Used for route and drop-off evidence.</p></div>
                    <button type="button" className="text-xs font-black text-teal-700" onClick={locate}>{lat && lng ? "Update" : "Use location"}</button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="text-xs font-semibold text-slate-600">Latitude<input required type="number" min="-90" max="90" step="any" className="field" value={lat} onChange={(e) => setLat(e.target.value)} /></label>
                    <label className="text-xs font-semibold text-slate-600">Longitude<input required type="number" min="-180" max="180" step="any" className="field" value={lng} onChange={(e) => setLng(e.target.value)} /></label>
                  </div>
                  <label className="block text-sm font-semibold text-slate-700">Instructions<input className="field" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Gate, floor, landmark…" /></label>
                  <button className="btn w-full py-3" disabled={busy}>{busy ? "Placing order…" : user ? "Place order →" : "Sign in to order"}</button>
                </form>
              )}
            </div>
          </aside>
        </div>
      </section>

      <section className="page-shell pt-8">
        <div className="grid gap-4 rounded-[2rem] border border-slate-200/70 bg-white/80 p-6 shadow-sm backdrop-blur sm:grid-cols-3">
          {[['Transparent timeline', 'Customers, partners, riders, and support see the parts of the same operational story relevant to them.'], ['Context before blame', 'Zone conditions and route evidence help avoid blaming a merchant or rider when an external cause is stronger.'], ['AI with guardrails', 'AI can explain evidence, while trained models and business rules remain responsible for operational decisions.']].map(([title, text]) => (
            <div key={title} className="rounded-2xl bg-slate-50 p-4">
              <p className="font-black text-slate-950">{title}</p>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

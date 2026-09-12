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
      <button type="button" className="qty-btn" aria-label={`Remove one ${name}`} onClick={() => onChange(-1)}>
        −
      </button>
      <span className="inline-block w-5 text-center text-sm font-semibold">{count}</span>
      <button type="button" className="qty-btn-dark" aria-label={`Add one ${name}`} onClick={() => onChange(1)}>
        +
      </button>
    </div>
  );
}

const HOW = [
  { icon: "🛒", title: "Order", text: "Choose a kitchen, build your basket, and place the order with a verified customer account." },
  { icon: "👨‍🍳", title: "Prepare", text: "The merchant accepts, prepares, packs, and hands the order to an assigned rider." },
  { icon: "🛵", title: "Track", text: "Rider pickup, route points, delivery time, and drop-off location become part of the evidence trail." },
  { icon: "⚖️", title: "Resolve", text: "If there is a problem, ResolveX combines timing, route, zone, photo, and claim-history signals for a fair outcome." },
];

const FAQ = [
  ["What happens if my delivery is late?", "ResolveX compares the promised delivery time with the recorded preparation, pickup, route, and delivery timestamps. If the issue is clear, the case can be resolved automatically; otherwise it moves to support review."],
  ["Can a merchant dispute a decision?", "Yes. Merchant partners can review the evidence, accept the verdict, or dispute it with a reason. Disputed cases are sent to support for mediation."],
  ["Do photos decide who is at fault?", "No. Photos are used as supporting evidence for complaints such as damaged or wrong items. Operational fault still comes from delivery timing, rider-route, zone, and other evidence."],
  ["What if delays affect a whole area?", "A zone-wide disruption can be detected before a complaint is raised. Affected customers can receive a delay notice, and neither the merchant nor rider is blamed when the evidence points to an external cause."],
];

export default function Storefront() {
  const { user, role } = useAuth();
  const navigate = useNavigate();
  const orderRef = useRef(null);
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [zone, setZone] = useState("all");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [activeDemoStep, setActiveDemoStep] = useState(0);
  const [openFaq, setOpenFaq] = useState(0);
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

  useEffect(() => {
    const timer = setInterval(() => setActiveDemoStep((step) => (step + 1) % HOW.length), 2600);
    return () => clearInterval(timer);
  }, []);

  const products = catalog?.products ?? [];
  const merchants = catalog?.merchants ?? [];
  const selectedMerchant = merchants.find((m) => m.id === basket.merchant);
  const zones = useMemo(() => {
    const ids = Array.from(new Set(merchants.map((m) => m.zone_id).filter((z) => z && /^ZONE_/i.test(z)))).sort();
    return ids.length ? ["all", ...ids] : [];
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

  function quantity(id, change) {
    setBasket((b) => ({ ...b, items: { ...b.items, [id]: Math.max(0, Math.min(20, (b.items[id] || 0) + change)) } }));
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
      () => setError("Location permission was not granted. Enter your delivery coordinates below.")
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
        items: Object.entries(basket.items).filter(([, qty]) => qty > 0).map(([product_id, qty]) => ({ product_id, qty })),
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
    <div className="relative min-h-[calc(100vh-3.6rem)] overflow-hidden bg-slate-50">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(251,191,36,0.14),_transparent_26%),linear-gradient(180deg,#fbfaf7_0%,#f8fafc_38%,#f1f5f9_100%)]" aria-hidden="true" />
      <div className="relative mx-auto max-w-7xl px-4 py-5 sm:px-6">
        <section className="relative overflow-hidden rounded-[2rem] bg-slate-950 text-white shadow-[0_30px_100px_-45px_rgba(15,23,42,0.9)]">
          <div className="pointer-events-none absolute -right-10 -top-24 h-72 w-72 rounded-full bg-teal-400/20 blur-3xl" />
          <div className="pointer-events-none absolute bottom-0 left-1/3 h-56 w-56 rounded-full bg-amber-300/10 blur-3xl" />
          <div className="relative grid gap-8 px-6 py-9 sm:px-9 lg:grid-cols-[1.15fr_.85fr] lg:items-center lg:py-12">
            <div>
              <div className="mb-4 flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">Live delivery evidence</span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">Fair claims</span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">Real-time operations</span>
              </div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-teal-300">ResolveX · last-mile delivery intelligence</p>
              <h1 className="font-serif mt-3 max-w-3xl text-4xl leading-[1.02] tracking-tight sm:text-5xl lg:text-6xl">
                Food delivery that stays <span className="italic text-teal-200">accountable</span> from checkout to claim.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-relaxed text-slate-300">
                Order from a restaurant, watch preparation and delivery unfold, and get a transparent resolution when something goes wrong. ResolveX turns timestamps, rider routes, zone conditions, photos, and claim history into one evidence-backed decision.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <button onClick={() => orderRef.current?.scrollIntoView({ behavior: "smooth" })} className="rounded-full bg-teal-300 px-5 py-2.5 text-sm font-bold text-slate-950 transition hover:-translate-y-0.5 hover:bg-teal-200">
                  Start an order
                </button>
                {!user ? (
                  <Link to="/signup" className="rounded-full border border-white/15 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10">Create account</Link>
                ) : (
                  <Link to="/my-orders" className="rounded-full border border-white/15 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10">View my orders</Link>
                )}
              </div>
              <div className="mt-8 grid max-w-2xl grid-cols-3 gap-3">
                {[['5', 'evidence engines'], ['4', 'delivery roles'], ['1', 'shared case timeline']].map(([value, label]) => (
                  <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 backdrop-blur">
                    <p className="text-2xl font-bold text-white">{value}</p>
                    <p className="text-xs text-slate-400">{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="rounded-[1.8rem] border border-white/10 bg-white/[0.06] p-4 backdrop-blur-xl">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-teal-300">Live case preview</p>
                    <h2 className="mt-1 text-lg font-semibold">Order #A12F9C</h2>
                  </div>
                  <span className="rounded-full bg-amber-300/15 px-3 py-1 text-xs font-semibold text-amber-200">Analysis active</span>
                </div>
                <div className="mt-5 space-y-3">
                  {HOW.map((step, index) => (
                    <button key={step.title} onClick={() => setActiveDemoStep(index)} className={`w-full rounded-2xl border p-3 text-left transition ${index === activeDemoStep ? "border-teal-300/50 bg-teal-300/10" : "border-white/10 bg-black/10 hover:bg-white/5"}`}>
                      <div className="flex items-start gap-3">
                        <span className="text-xl">{step.icon}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="font-semibold">{index + 1}. {step.title}</p>
                            <span className={`h-2.5 w-2.5 rounded-full ${index <= activeDemoStep ? "bg-teal-300" : "bg-slate-600"}`} />
                          </div>
                          <p className="mt-1 text-xs leading-relaxed text-slate-400">{step.text}</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[['⚡', 'Proactive detection', 'Late orders can be flagged before the customer complains.'], ['📍', 'Route evidence', 'GPS points reveal detours, long stops, and drop-off accuracy.'], ['🌐', 'Zone awareness', 'Area-wide disruptions are separated from merchant or rider fault.'], ['💸', 'Fast resolution', 'Valid low-risk claims can move directly to refund.']].map(([icon, title, text]) => (
            <article key={title} className="group rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-xl text-white transition group-hover:scale-105">{icon}</div>
              <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{text}</p>
            </article>
          ))}
        </section>

        <section className="mt-8 grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
          <div className="rounded-[1.8rem] border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">How ResolveX decides</p>
            <h2 className="font-serif mt-2 text-3xl tracking-tight text-slate-900">One decision, built from multiple signals.</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">The platform does not rely on a single photo or a single timestamp. It builds a case from the whole delivery journey and keeps operational fault separate from claim-risk screening.</p>
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              {['Preparation timing', 'Rider route', 'Zone-wide delays', 'Photo evidence', 'Claim history', 'Model confidence'].map((item) => (
                <div key={item} className="rounded-2xl bg-slate-50 px-3 py-2.5 text-sm font-medium text-slate-700">✓ {item}</div>
              ))}
            </div>
          </div>
          <div className="rounded-[1.8rem] bg-gradient-to-br from-teal-700 to-slate-950 p-6 text-white shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-200">Transparent outcomes</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[['Merchant responsible', 'Preparation or packing evidence points to the kitchen.'], ['Rider responsible', 'Route or delivery evidence points to the rider.'], ['Neither at fault', 'External or zone-wide conditions explain the problem.'], ['Support review', 'Conflicting or low-confidence evidence goes to a human.']].map(([title, text]) => (
                <div key={title} className="rounded-2xl border border-white/10 bg-white/[0.06] p-4">
                  <h3 className="font-semibold">{title}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {error && <p role="alert" className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <section ref={orderRef} className="mt-10 scroll-mt-20">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Order flow</p>
              <h2 className="font-serif mt-1 text-3xl tracking-tight text-slate-900">Choose a kitchen and build your order.</h2>
              <p className="mt-1 text-sm text-slate-500">Every action from checkout onward becomes part of the operational record used by ResolveX.</p>
            </div>
            {user && role === 'customer' && <Link to="/my-orders" className="btn-secondary">Track existing orders</Link>}
          </div>

          <div className="grid gap-5 lg:grid-cols-12">
            <div className="space-y-5 lg:col-span-8">
              <section>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="font-serif text-xl tracking-tight text-slate-800">1. Pick a kitchen</h3>
                  {selectedMerchant && <button type="button" className="shrink-0 text-sm font-medium text-teal-800" onClick={() => setPickerOpen((open) => !open)}>{showPicker ? "Hide list" : "Change kitchen"}</button>}
                </div>
                {selectedMerchant && !showPicker && (
                  <div className="flex items-center gap-4 rounded-[1.35rem] border border-teal-200/80 bg-white p-4 shadow-sm">
                    <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-100 to-amber-50 text-xl">🍽️</span>
                    <div className="min-w-0 flex-1">
                      <p className="font-serif text-lg leading-tight">{merchantParts(selectedMerchant.name).title}</p>
                      <p className="mt-1 text-xs text-slate-500">{selectedMerchant.avg_prep_minutes} min prep{selectedMerchant.zone_id ? ` · ${selectedMerchant.zone_id}` : ""}</p>
                      {merchantParts(selectedMerchant.name).note && <p className="mt-1 text-xs text-amber-800">{merchantParts(selectedMerchant.name).note}</p>}
                    </div>
                    <button type="button" className="shrink-0 text-sm font-medium text-teal-800" onClick={() => setPickerOpen(true)}>Change</button>
                  </div>
                )}
                {showPicker && (
                  <div className="overflow-hidden rounded-[1.35rem] border border-slate-200 bg-white p-3 shadow-sm">
                    <input className="field mt-0 rounded-2xl border-slate-200 bg-white" type="search" placeholder="Search by restaurant name or zone" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search restaurants" />
                    {zones.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{zones.map((z) => <button key={z} type="button" onClick={() => setZone(z)} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${zone === z ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600"}`}>{z === "all" ? "All zones" : z}</button>)}</div>}
                    {!catalog && <p className="mt-3 text-sm text-slate-400">Loading kitchens…</p>}
                    <div className="scroll-pane mt-2 h-52" role="listbox" aria-label="Choose a restaurant">
                      {filteredMerchants.map((m) => {
                        const { title, note } = merchantParts(m.name);
                        const active = basket.merchant === m.id;
                        return <button key={m.id} type="button" role="option" aria-selected={active} onClick={() => pickMerchant(m.id)} className={`block w-full rounded-2xl px-3 py-2.5 text-left ${active ? "bg-slate-950 text-white" : "hover:bg-slate-50"}`}><span className="block font-medium">{title}</span><span className={`mt-0.5 block text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>{m.avg_prep_minutes} min prep{m.zone_id ? ` · ${m.zone_id}` : ""}{note ? ` · ${note}` : ""}</span></button>;
                      })}
                      {catalog && !filteredMerchants.length && <p className="p-3 text-center text-sm text-slate-500">No kitchens match that search.</p>}
                    </div>
                  </div>
                )}
              </section>

              <section>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-serif text-xl tracking-tight text-slate-800">2. Build your basket</h3>
                  <div className="flex flex-wrap gap-1 rounded-full bg-white p-1 ring-1 ring-slate-200/80">
                    {categories.map((c) => <button key={c} type="button" onClick={() => setCategory(c)} className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${category === c ? "bg-slate-950 text-white shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>{c === "all" ? "All" : c}</button>)}
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {visible.map((p) => (
                    <article key={p.id} className="group flex items-center gap-4 rounded-[1.35rem] border border-slate-200/80 bg-white p-3.5 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md">
                      <div className="inline-flex h-[4.25rem] w-[4.25rem] shrink-0 items-center justify-center rounded-[1.15rem] bg-gradient-to-br from-teal-50 via-white to-amber-50 text-4xl transition group-hover:scale-105">{p.emoji}</div>
                      <div className="min-w-0 flex-1"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal-700/80">{p.category}</p><h4 className="truncate font-semibold text-slate-900">{p.name}</h4><p className="mt-0.5 text-sm text-slate-600">LKR {p.price.toLocaleString()}</p></div>
                      {basket.items[p.id] > 0 ? <QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} /> : <button type="button" className="shrink-0 rounded-full bg-slate-950 px-3.5 py-1.5 text-sm font-semibold leading-5 text-white disabled:opacity-40" disabled={!basket.merchant} onClick={() => quantity(p.id, 1)}>Add</button>}
                    </article>
                  ))}
                </div>
                {!basket.merchant && catalog && <p className="mt-3 text-sm text-slate-500">Choose a restaurant above to start adding dishes.</p>}
              </section>
            </div>

            <aside className="h-fit overflow-hidden rounded-[1.5rem] border border-slate-200/80 bg-white shadow-sm lg:col-span-4 lg:sticky lg:top-20">
              <div className="bg-slate-950 px-5 py-4 text-white"><p className="text-[11px] uppercase tracking-[0.2em] text-teal-300">3. Checkout</p><h3 className="font-serif mt-1 text-2xl">Your basket</h3>{selectedMerchant && <p className="mt-1 text-xs text-slate-400">{merchantParts(selectedMerchant.name).title}</p>}</div>
              <div className="p-5">
                {!total && <p className="my-2 text-sm leading-relaxed text-slate-500">Your basket is empty. Pick a kitchen and add a dish to begin.</p>}
                <div className="divide-y divide-slate-100">{basketItems.map((p) => <div key={p.id} className="py-3"><p className="text-sm font-medium">{p.name}</p><div className="mt-2 flex items-center justify-between"><QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} /><span className="text-sm tabular-nums">LKR {(p.price * basket.items[p.id]).toLocaleString()}</span></div></div>)}</div>
                <p className="flex justify-between border-t border-slate-100 py-3 font-semibold"><span>Total</span><span className="tabular-nums">LKR {total.toLocaleString()}</span></p>
                {total > 0 && (
                  <form onSubmit={place} className="space-y-3">
                    <h4 className="text-sm font-semibold">Delivery details</h4>
                    <label className="block text-sm">Street address<textarea required minLength={8} className="field" rows={2} value={address} onChange={(e) => setAddress(e.target.value)} /></label>
                    <label className="block text-sm">Contact number<input required minLength={7} className="field" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
                    <div className="flex items-center justify-between gap-2"><button type="button" className="text-sm font-medium text-teal-800" onClick={locate}>Use my location</button>{lat && lng && <span className="text-xs text-emerald-700">Pin saved</span>}</div>
                    <div className="grid grid-cols-2 gap-2"><label className="text-sm">Latitude<input required type="number" min="-90" max="90" step="any" className="field" value={lat} onChange={(e) => setLat(e.target.value)} /></label><label className="text-sm">Longitude<input required type="number" min="-180" max="180" step="any" className="field" value={lng} onChange={(e) => setLng(e.target.value)} /></label></div>
                    <label className="block text-sm">Instructions<input className="field" placeholder="Gate, floor, landmark…" value={instructions} onChange={(e) => setInstructions(e.target.value)} /></label>
                    <button className="w-full rounded-full bg-teal-700 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:opacity-50" disabled={busy}>{busy ? "Placing order…" : user ? "Place order" : "Sign in to order"}</button>
                  </form>
                )}
              </div>
            </aside>
          </div>
        </section>

        <section className="mt-10 rounded-[1.8rem] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-6 lg:grid-cols-[.8fr_1.2fr]">
            <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Questions</p><h2 className="font-serif mt-2 text-3xl tracking-tight text-slate-900">Know what happens before you need support.</h2><p className="mt-3 text-sm leading-relaxed text-slate-500">The customer, merchant, rider, ops, and support views all use the same underlying order evidence, so a case can be traced from checkout to final outcome.</p></div>
            <div className="space-y-2">
              {FAQ.map(([question, answer], index) => <button key={question} type="button" onClick={() => setOpenFaq(openFaq === index ? -1 : index)} className="w-full rounded-2xl border border-slate-200 p-4 text-left transition hover:border-teal-200"><div className="flex items-center justify-between gap-4"><span className="font-semibold text-slate-900">{question}</span><span className="text-xl text-slate-400">{openFaq === index ? '−' : '+'}</span></div>{openFaq === index && <p className="mt-3 text-sm leading-relaxed text-slate-600">{answer}</p>}</button>)}
            </div>
          </div>
        </section>

        <section className="mt-8 mb-4 rounded-[1.8rem] bg-slate-950 px-6 py-8 text-white sm:px-8">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-300">Ready to try the flow?</p><h2 className="font-serif mt-2 text-3xl">Order. Track. Report. Resolve.</h2><p className="mt-2 max-w-2xl text-sm text-slate-400">ResolveX makes every last-mile action visible enough to explain what happened and who should act next.</p></div>
            <button onClick={() => orderRef.current?.scrollIntoView({ behavior: "smooth" })} className="rounded-full bg-teal-300 px-5 py-2.5 text-sm font-bold text-slate-950 hover:bg-teal-200">Browse menu</button>
          </div>
        </section>
      </div>
    </div>
  );
}

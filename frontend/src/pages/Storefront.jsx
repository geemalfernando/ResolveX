import { useEffect, useMemo, useState } from "react";
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

export default function Storefront() {
  const { user, role } = useAuth();
  const navigate = useNavigate();
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
  const categories = useMemo(
    () => ["all", ...Array.from(new Set(products.map((p) => p.category)))],
    [products]
  );
  const visible = products.filter((p) => category === "all" || p.category === category);
  const total = products.reduce((sum, p) => sum + p.price * (basket.items[p.id] || 0), 0);
  const basketItems = products.filter((p) => basket.items[p.id] > 0);

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
    <div className="relative min-h-[calc(100vh-3.6rem)]">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(13,148,136,0.16),_transparent_52%),linear-gradient(180deg,#f7f4ee_0%,#f1f5f9_42%)]"
        aria-hidden="true"
      />
      <div className="relative mx-auto flex max-w-7xl flex-col px-4 py-5 sm:px-6">
        <section className="relative mb-5 overflow-hidden rounded-[1.75rem] bg-slate-950 text-white shadow-[0_24px_80px_-40px_rgba(15,23,42,0.65)]">
          <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-teal-400/25 blur-3xl" />
          <div className="pointer-events-none absolute bottom-0 left-1/3 h-32 w-32 rounded-full bg-amber-300/15 blur-3xl" />
          <div className="relative flex flex-wrap items-end justify-between gap-5 px-6 py-6 sm:px-8">
            <div className="max-w-xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-teal-300">Colombo evenings</p>
              <h1 className="font-serif mt-2 text-4xl leading-[1.05] tracking-tight sm:text-[2.75rem]">
                Dinner, <span className="italic text-teal-200">beautifully</span> accounted for.
              </h1>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-300">
                Choose a kitchen, add a few dishes, and follow every stage — with a fair outcome if something goes wrong.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <div className="hidden gap-5 text-[11px] uppercase tracking-[0.16em] text-slate-400 sm:flex">
                <span>Tracked live</span>
                <span>Fair refunds</span>
                <span>Demo only</span>
              </div>
              {!user && (
                <Link to="/signup" className="rounded-full bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950">
                  Create an account
                </Link>
              )}
            </div>
          </div>
        </section>

        {error && (
          <p role="alert" className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}

        <div className="grid gap-5 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-8">
            <section>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="font-serif text-xl tracking-tight text-slate-800">Kitchen</h2>
                {selectedMerchant && (
                  <button type="button" className="shrink-0 text-sm font-medium text-teal-800" onClick={() => setPickerOpen((open) => !open)}>
                    {showPicker ? "Hide list" : "Change kitchen"}
                  </button>
                )}
              </div>

              {selectedMerchant && !showPicker && (
                <div className="flex items-center gap-4 rounded-[1.35rem] border border-teal-200/80 bg-white p-4 shadow-sm">
                  <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-100 to-amber-50 text-xl" aria-hidden="true">
                    🍽️
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-serif text-lg leading-tight">{merchantParts(selectedMerchant.name).title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {selectedMerchant.avg_prep_minutes} min prep
                      {selectedMerchant.zone_id ? ` · ${selectedMerchant.zone_id}` : ""}
                    </p>
                    {merchantParts(selectedMerchant.name).note && (
                      <p className="mt-1 text-xs text-amber-800">{merchantParts(selectedMerchant.name).note}</p>
                    )}
                  </div>
                  <button type="button" className="shrink-0 text-sm font-medium text-teal-800" onClick={() => setPickerOpen(true)}>
                    Change
                  </button>
                </div>
              )}

              {showPicker && (
                <div className="overflow-hidden rounded-[1.35rem] border border-slate-200 bg-white p-3 shadow-sm">
                  <input
                    className="field mt-0 rounded-2xl border-slate-200 bg-white"
                    type="search"
                    placeholder="Search by name or zone"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Search restaurants"
                  />
                  {zones.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {zones.map((z) => (
                        <button
                          key={z}
                          type="button"
                          onClick={() => setZone(z)}
                          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                            zone === z ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {z === "all" ? "All zones" : z}
                        </button>
                      ))}
                    </div>
                  )}
                  {!catalog && <p className="mt-3 text-sm text-slate-400">Loading kitchens…</p>}
                  <div className="scroll-pane mt-2 h-52" role="listbox" aria-label="Choose a restaurant">
                    {filteredMerchants.map((m) => {
                      const { title, note } = merchantParts(m.name);
                      const active = basket.merchant === m.id;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          role="option"
                          aria-selected={active}
                          onClick={() => pickMerchant(m.id)}
                          className={`block w-full rounded-2xl px-3 py-2.5 text-left ${
                            active ? "bg-slate-950 text-white" : "hover:bg-slate-50"
                          }`}
                        >
                          <span className="block font-medium">{title}</span>
                          <span className={`mt-0.5 block text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>
                            {m.avg_prep_minutes} min prep{m.zone_id ? ` · ${m.zone_id}` : ""}
                            {note ? ` · ${note}` : ""}
                          </span>
                        </button>
                      );
                    })}
                    {catalog && !filteredMerchants.length && (
                      <p className="p-3 text-center text-sm text-slate-500">No kitchens match that search.</p>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-serif text-xl tracking-tight text-slate-800">Menu</h2>
                <div className="flex flex-wrap gap-1 rounded-full bg-white p-1 ring-1 ring-slate-200/80">
                  {categories.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCategory(c)}
                      className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${
                        category === c ? "bg-slate-950 text-white shadow-sm" : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {c === "all" ? "All" : c}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {visible.map((p) => (
                  <article
                    key={p.id}
                    className="flex items-center gap-4 rounded-[1.35rem] border border-slate-200/80 bg-white p-3.5 shadow-sm"
                  >
                    <div
                      className="inline-flex h-[4.25rem] w-[4.25rem] shrink-0 items-center justify-center rounded-[1.15rem] bg-gradient-to-br from-teal-50 via-white to-amber-50 text-4xl"
                      aria-hidden="true"
                    >
                      {p.emoji}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal-700/80">{p.category}</p>
                      <h3 className="truncate font-semibold text-slate-900">{p.name}</h3>
                      <p className="mt-0.5 text-sm text-slate-600">LKR {p.price.toLocaleString()}</p>
                    </div>
                    {basket.items[p.id] > 0 ? (
                      <QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} />
                    ) : (
                      <button
                        type="button"
                        className="shrink-0 rounded-full bg-slate-950 px-3.5 py-1.5 text-sm font-semibold leading-5 text-white disabled:opacity-40"
                        disabled={!basket.merchant}
                        onClick={() => quantity(p.id, 1)}
                      >
                        Add
                      </button>
                    )}
                  </article>
                ))}
              </div>
              {!basket.merchant && catalog && (
                <p className="mt-3 text-sm text-slate-500">Choose a restaurant above to start adding dishes.</p>
              )}
            </section>
          </div>

          <aside className="h-fit overflow-hidden rounded-[1.5rem] border border-slate-200/80 bg-white shadow-sm lg:col-span-4 lg:sticky lg:top-20">
            <div className="bg-slate-950 px-5 py-4 text-white">
              <p className="text-[11px] uppercase tracking-[0.2em] text-teal-300">Your order</p>
              <h2 className="font-serif mt-1 text-2xl">Basket</h2>
              {selectedMerchant && (
                <p className="mt-1 text-xs text-slate-400">{merchantParts(selectedMerchant.name).title}</p>
              )}
            </div>
            <div className="p-5">
              {!total && <p className="my-2 text-sm leading-relaxed text-slate-500">Your basket is empty. A kitchen and a dish, and this fills in.</p>}
              <div className="divide-y divide-slate-100">
                {basketItems.map((p) => (
                  <div key={p.id} className="py-3">
                    <p className="text-sm font-medium">{p.name}</p>
                    <div className="mt-2 flex items-center justify-between">
                      <QtyStepper name={p.name} count={basket.items[p.id]} onChange={(delta) => quantity(p.id, delta)} />
                      <span className="text-sm tabular-nums">LKR {(p.price * basket.items[p.id]).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
              <p className="flex justify-between border-t border-slate-100 py-3 font-semibold">
                <span>Total</span>
                <span className="tabular-nums">LKR {total.toLocaleString()}</span>
              </p>
              {total > 0 && (
                <form onSubmit={place} className="space-y-3">
                  <h3 className="text-sm font-semibold">Delivery</h3>
                  <label className="block text-sm">
                    Street address
                    <textarea required minLength={8} className="field" rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />
                  </label>
                  <label className="block text-sm">
                    Contact number
                    <input required minLength={7} className="field" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
                  </label>
                  <div className="flex items-center justify-between gap-2">
                    <button type="button" className="text-sm font-medium text-teal-800" onClick={locate}>
                      Use my location
                    </button>
                    {lat && lng && <span className="text-xs text-emerald-700">Pin saved</span>}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="text-sm">
                      Latitude
                      <input required type="number" min="-90" max="90" step="any" className="field" value={lat} onChange={(e) => setLat(e.target.value)} />
                    </label>
                    <label className="text-sm">
                      Longitude
                      <input required type="number" min="-180" max="180" step="any" className="field" value={lng} onChange={(e) => setLng(e.target.value)} />
                    </label>
                  </div>
                  <label className="block text-sm">
                    Instructions
                    <input className="field" value={instructions} onChange={(e) => setInstructions(e.target.value)} />
                  </label>
                  <button className="w-full rounded-full bg-teal-700 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50" disabled={busy}>
                    {busy ? "Placing order…" : user ? "Place demo order" : "Sign in to order"}
                  </button>
                </form>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

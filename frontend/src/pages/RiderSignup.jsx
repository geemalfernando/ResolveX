import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { supabase } from "../lib/supabaseClient";

export default function RiderSignup() {
  const navigate = useNavigate();
    const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    phone: "",
    vehicle: "bike",
    lat: "",
    lng: "",
  });
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function useLocation() {
    setError("");
    if (!navigator.geolocation) {
      setError("Location is not supported in this browser.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        update("lat", position.coords.latitude.toFixed(6));
        update("lng", position.coords.longitude.toFixed(6));
        setLocating(false);
      },
      (err) => {
        setError(err.message || "Could not get your location.");
        setLocating(false);
      },
      { enableHighAccuracy: true, maximumAge: 10000 }
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/commerce/riders/join", {
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim(),
        vehicle: form.vehicle,
        lat: form.lat ? Number(form.lat) : null,
        lng: form.lng ? Number(form.lng) : null,
      });

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: form.email.trim(),
        password: form.password,
      });
      if (signInError) throw signInError;
      navigate("/rider");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell py-8 sm:py-12">
      <div className="grid overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-xl lg:grid-cols-[.9fr_1.1fr]">
        <section className="bg-slate-950 p-7 text-white sm:p-10">
          <p className="text-xs font-black uppercase tracking-[0.22em] text-teal-300">Ride with ResolveX</p>
          <h1 className="mt-4 text-4xl font-black tracking-tight sm:text-5xl">Join the delivery team.</h1>
          <p className="mt-4 max-w-lg text-sm leading-relaxed text-slate-300">
            Create your rider account, share your location, receive nearby packed orders, and open customer directions from your delivery workspace.
          </p>
          <div className="mt-8 space-y-3 text-sm text-slate-200">
            <p>✓ Start immediately after signup</p>
            <p>✓ No email verification step</p>
            <p>✓ Nearby orders can be assigned automatically</p>
            <p>✓ Reject an assignment and the system can reassign it</p>
          </div>
        </section>

        <form onSubmit={submit} className="p-6 sm:p-10">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="kicker">Rider application</p>
              <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">Create rider account</h2>
            </div>
            <Link to="/login" className="text-sm font-bold text-teal-700">Sign in</Link>
          </div>

          {error && <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-semibold text-slate-700">
              Full name
              <input required minLength={2} className="field" value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Kasun Perera" />
            </label>
            <label className="text-sm font-semibold text-slate-700">
              Phone
              <input required minLength={7} className="field" value={form.phone} onChange={(e) => update("phone", e.target.value)} placeholder="+94 77 123 4567" />
            </label>
            <label className="text-sm font-semibold text-slate-700 sm:col-span-2">
              Email
              <input required type="email" className="field" autoComplete="email" value={form.email} onChange={(e) => update("email", e.target.value)} placeholder="rider@example.com" />
            </label>
            <label className="text-sm font-semibold text-slate-700 sm:col-span-2">
              Password
              <input required minLength={12} type="password" className="field" autoComplete="new-password" value={form.password} onChange={(e) => update("password", e.target.value)} placeholder="At least 12 characters" />
            </label>
            <label className="text-sm font-semibold text-slate-700 sm:col-span-2">
              Vehicle
              <select className="field" value={form.vehicle} onChange={(e) => update("vehicle", e.target.value)}>
                <option value="bike">Bike</option>
                <option value="scooter">Scooter</option>
                <option value="car">Car</option>
              </select>
            </label>
          </div>

          <div className="mt-5 rounded-2xl bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-slate-900">Current location</p>
                <p className="text-xs text-slate-500">Your delivery zone is assigned from this pin. You do not choose a zone.</p>
              </div>
              <button type="button" className="btn-secondary" onClick={useLocation} disabled={locating}>
                {locating ? "Getting location…" : "Use my location"}
              </button>
            </div>
            {form.lat && form.lng && <p className="mt-2 text-xs font-semibold text-emerald-700">Location ready</p>}
          </div>

          <button className="btn mt-6 w-full py-3" disabled={busy}>
            {busy ? "Creating rider account…" : "Join as a rider →"}
          </button>
          <p className="mt-3 text-center text-xs text-slate-500">Your account is activated immediately after signup.</p>
        </form>
      </div>
    </div>
  );
}

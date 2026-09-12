import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const HOME_BY_ROLE = {
  customer: "/",
  ops: "/ops",
  partner: "/merchant",
  rider: "/rider",
  support: "/claims",
  admin: "/admin",
};

const WORKSPACES = [
  ["Customer", "Order, track, and report delivery issues."],
  ["Merchant", "Prepare orders and review partner disputes."],
  ["Rider", "See assigned deliveries and share route evidence."],
  ["Operations", "Watch delays, zones, and live incidents."],
];

export default function Login() {
  const { user, role, signIn, error: authError, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (user && role) {
      navigate(location.state?.from ?? HOME_BY_ROLE[role] ?? "/", { replace: true });
    }
  }, [user, role, navigate, location.state]);

  if (!loading && user && role) return <Navigate to={HOME_BY_ROLE[role] ?? "/"} replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setError(err.message || "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden px-4 py-8 sm:px-6 lg:grid lg:grid-cols-[1.05fr_.95fr] lg:items-stretch lg:py-10">
      <div className="pointer-events-none absolute -left-24 top-10 h-80 w-80 rounded-full bg-teal-300/15 blur-3xl" />
      <div className="pointer-events-none absolute -right-20 bottom-0 h-80 w-80 rounded-full bg-amber-200/20 blur-3xl" />

      <section className="relative mx-auto hidden w-full max-w-3xl overflow-hidden rounded-[2rem] bg-slate-950 p-10 text-white shadow-[0_30px_100px_-45px_rgba(15,23,42,.9)] lg:flex lg:flex-col lg:justify-between">
        <div>
          <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.2em] text-teal-300">
            ResolveX workspace
          </span>
          <h1 className="mt-6 max-w-xl text-5xl font-black leading-[1.02] tracking-tight">
            One login. The right workspace for every delivery role.
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300">
            ResolveX routes you directly to the tools your role needs while keeping order evidence, claims, disputes, and operational decisions connected.
          </p>
        </div>

        <div className="mt-10 grid gap-3 sm:grid-cols-2">
          {WORKSPACES.map(([title, text], index) => (
            <div key={title} className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur">
              <div className="flex items-start gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-teal-300/15 text-sm font-black text-teal-200">{index + 1}</span>
                <div>
                  <p className="font-bold">{title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-400">{text}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 flex items-center gap-2 text-xs text-slate-400">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse-soft" />
          Live operational evidence stays linked to each order.
        </div>
      </section>

      <div className="relative mx-auto flex w-full max-w-xl items-center justify-center lg:px-8">
        <form onSubmit={submit} className="glass-card w-full p-6 sm:p-8 lg:p-10">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-lg font-black text-white shadow-lg">X</span>
            <div>
              <p className="kicker">Welcome back</p>
              <p className="text-sm font-semibold text-slate-500">Secure role-based access</p>
            </div>
          </div>

          <h2 className="mt-7 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">Sign in to ResolveX</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">
            Continue to your customer, merchant, rider, operations, support, or admin workspace.
          </p>

          {(error || authError) && (
            <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-700" role="alert">
              <p className="font-semibold">Could not sign you in</p>
              <p className="mt-1 text-xs leading-relaxed">{error || authError}</p>
            </div>
          )}

          <label className="mt-6 block text-sm font-semibold text-slate-700">
            Email address
            <input
              className="field"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
            />
          </label>

          <label className="mt-4 block text-sm font-semibold text-slate-700">
            Password
            <div className="relative">
              <input
                className="field pr-20"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="Your password"
              />
              <button
                type="button"
                onClick={() => setShowPassword((show) => !show)}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-bold text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button className="btn mt-6 w-full py-3" disabled={busy} type="submit">
            {busy ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Signing in…
              </>
            ) : (
              <>Sign in <span aria-hidden="true">→</span></>
            )}
          </button>

          <div className="mt-5 flex items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-200" />
            New to ResolveX?
            <span className="h-px flex-1 bg-slate-200" />
          </div>

          <Link to="/signup" className="btn-secondary mt-4 w-full">
            Create a customer account
          </Link>

          <p className="mt-5 text-center text-[11px] leading-relaxed text-slate-400">
            Your session determines which workspace and order data you can access.
          </p>
        </form>
      </div>
    </div>
  );
}

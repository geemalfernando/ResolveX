import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabaseClient";

const BENEFITS = [
  ["Live order timeline", "Follow preparation, pickup, route, and delivery stages from one place."],
  ["Evidence-backed claims", "Report a problem with photos and keep the full delivery trail attached."],
  ["Fair outcomes", "ResolveX separates merchant, rider, and external causes using multiple signals."],
];

export default function Signup() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const passwordScore = useMemo(() => {
    let score = 0;
    if (password.length >= 8) score += 1;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
    if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
    return score;
  }, [password]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    setSuccess(false);
    try {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { data: { name }, emailRedirectTo: window.location.origin + "/login" },
      });
      if (error) throw error;
      if (data.session) navigate("/");
      else {
        setSuccess(true);
        setMessage("Check your email to confirm your account, then sign in to place your order.");
      }
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden px-4 py-8 sm:px-6 lg:grid lg:grid-cols-[.95fr_1.05fr] lg:items-stretch lg:py-10">
      <div className="pointer-events-none absolute -left-20 bottom-0 h-80 w-80 rounded-full bg-amber-200/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 top-10 h-80 w-80 rounded-full bg-teal-300/15 blur-3xl" />

      <div className="relative mx-auto flex w-full max-w-xl items-center justify-center lg:px-8">
        <form onSubmit={submit} className="glass-card w-full p-6 sm:p-8 lg:p-10">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-lg font-black text-white shadow-lg">X</span>
            <div>
              <p className="kicker">Create account</p>
              <p className="text-sm font-semibold text-slate-500">Customer access</p>
            </div>
          </div>

          <h1 className="mt-7 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">Start your ResolveX journey</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">
            Create a customer account to order, track deliveries, and submit evidence-backed claims when something goes wrong.
          </p>

          {message && (
            <div className={`mt-5 rounded-2xl border p-3.5 text-sm ${success ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-rose-200 bg-rose-50 text-rose-700"}`} role="status">
              <p className="font-semibold">{success ? "Almost there" : "Could not create account"}</p>
              <p className="mt-1 text-xs leading-relaxed">{message}</p>
            </div>
          )}

          <label className="mt-6 block text-sm font-semibold text-slate-700">
            Your name
            <input required minLength={2} className="field" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your full name" />
          </label>

          <label className="mt-4 block text-sm font-semibold text-slate-700">
            Email address
            <input required type="email" className="field" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </label>

          <label className="mt-4 block text-sm font-semibold text-slate-700">
            Password
            <div className="relative">
              <input
                required
                minLength={8}
                type={showPassword ? "text" : "password"}
                className="field pr-20"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
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

          <div className="mt-3">
            <div className="grid grid-cols-3 gap-1.5">
              {[0, 1, 2].map((index) => (
                <span key={index} className={`h-1.5 rounded-full transition ${index < passwordScore ? "bg-teal-500" : "bg-slate-200"}`} />
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Use 8+ characters. A mix of upper/lowercase, numbers, and symbols is stronger.
            </p>
          </div>

          <button disabled={busy} className="btn mt-6 w-full py-3">
            {busy ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Creating account…
              </>
            ) : (
              <>Create account <span aria-hidden="true">→</span></>
            )}
          </button>

          <p className="mt-5 text-center text-sm text-slate-500">
            Already registered? <Link className="font-bold text-teal-700 hover:text-teal-800" to="/login">Sign in</Link>
          </p>
        </form>
      </div>

      <section className="relative mx-auto mt-6 hidden w-full max-w-3xl overflow-hidden rounded-[2rem] bg-gradient-to-br from-teal-700 via-teal-800 to-slate-950 p-10 text-white shadow-[0_30px_100px_-45px_rgba(15,23,42,.9)] lg:flex lg:flex-col lg:justify-between">
        <div>
          <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.2em] text-teal-100">
            Built for transparent delivery
          </span>
          <h2 className="mt-6 max-w-xl text-5xl font-black leading-[1.02] tracking-tight">
            Order confidently. Keep the evidence if anything goes wrong.
          </h2>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-teal-50/80">
            Every meaningful delivery action can become part of a case timeline, so decisions are based on what actually happened instead of guesswork.
          </p>
        </div>

        <div className="mt-10 space-y-3">
          {BENEFITS.map(([title, text], index) => (
            <div key={title} className="flex gap-4 rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 text-sm font-black">0{index + 1}</span>
              <div>
                <p className="font-bold">{title}</p>
                <p className="mt-1 text-xs leading-relaxed text-teal-50/70">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

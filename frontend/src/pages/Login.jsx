import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const HOME_BY_ROLE = {
  customer: "/",
  ops: "/ops",
  partner: "/partner",
  support: "/support",
  admin: "/admin",
};

export default function Login() {
  const { user, role, signIn, error: authError, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (user && role) {
      navigate(location.state?.from ?? HOME_BY_ROLE[role] ?? "/", { replace: true });
    }
  }, [user, role]);

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
    <div className="min-h-[calc(100vh-65px)] grid place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border bg-white p-7 shadow-sm">
        <p className="text-sm font-semibold text-slate-500">ResolveX</p>
        <h1 className="mt-1 text-2xl font-bold">Sign in</h1>
        <p className="mt-2 text-sm text-slate-600">Your assigned role controls which dashboard and data you can access.</p>

        {(error || authError) && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error || authError}</p>}

        <label className="mt-5 block text-sm font-medium">
          Email
          <input className="field mt-1" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label className="mt-4 block text-sm font-medium">
          Password
          <input className="field mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        <button className="btn mt-6 w-full" disabled={busy} type="submit">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

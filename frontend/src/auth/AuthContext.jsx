import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { supabase, API_BASE_URL } from "../lib/supabaseClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadProfile(nextSession) {
    if (!nextSession?.user) {
      setProfile(null);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/commerce/me`, {headers: {Authorization: `Bearer ${nextSession.access_token}`}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not load your account');
      setProfile(data);
      setError('');
    } catch (err) { setProfile(null); setError(err.message); }
  }

  useEffect(() => {
    let mounted = true;
    supabase.auth.getSession().then(async ({ data, error }) => {
      if (!mounted) return;
      if (error) {
        await supabase.auth.signOut({ scope: "local" });
        setSession(null);
        setProfile(null);
        setLoading(false);
        return;
      }
      setSession(data.session ?? null);
      await loadProfile(data.session ?? null);
      if (mounted) setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange(async (_event, nextSession) => {
      setSession(nextSession);
      await loadProfile(nextSession);
      setLoading(false);
    });

    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  async function signIn(email, password) {
    setError("");
    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError) {
      setError(signInError.message);
      throw signInError;
    }
    setSession(data.session);
    await loadProfile(data.session);
    return data;
  }

  async function signOut() {
    await supabase.auth.signOut();
    setSession(null);
    setProfile(null);
  }

  const value = useMemo(
    () => ({ session, user: session?.user ?? null, profile, role: profile?.role ?? null, loading, error, signIn, signOut }),
    [session, profile, loading, error],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

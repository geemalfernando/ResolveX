import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabaseClient";

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

    const user = nextSession.user;
    const { data, error: profileError } = await supabase
      .from("user_profiles")
      .select("user_id,email,display_name,role,customer_id,merchant_id")
      .eq("user_id", user.id)
      .maybeSingle();

    if (profileError) {
      // The backend will still validate trusted app_metadata. Keeping this
      // fallback makes auth usable while the RBAC migration is being applied.
      const meta = user.app_metadata ?? {};
      setProfile({
        user_id: user.id,
        email: user.email,
        display_name: meta.display_name ?? user.email,
        role: meta.role ?? null,
        customer_id: meta.customer_id ?? null,
        merchant_id: meta.merchant_id ?? null,
      });
      return;
    }

    setProfile(
      data ?? {
        user_id: user.id,
        email: user.email,
        display_name: user.email,
        role: user.app_metadata?.role ?? null,
        customer_id: user.app_metadata?.customer_id ?? null,
        merchant_id: user.app_metadata?.merchant_id ?? null,
      },
    );
  }

  useEffect(() => {
    let mounted = true;
    supabase.auth.getSession().then(async ({ data }) => {
      if (!mounted) return;
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

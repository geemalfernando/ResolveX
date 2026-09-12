import { useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import Storefront from "./pages/Storefront.jsx";
import Signup from "./pages/Signup.jsx";
import OrderDashboard from "./pages/OrderDashboard.jsx";
import CustomerApp from "./pages/CustomerApp.jsx";
import OpsDashboard from "./pages/OpsDashboard.jsx";
import PartnerPortal from "./pages/PartnerPortal.jsx";
import SupportQueue from "./pages/SupportQueue.jsx";
import Admin from "./pages/Admin.jsx";
import ClaimRiskBoard from "./pages/ClaimRiskBoard.jsx";
import Login from "./pages/Login.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import XAssistant from "./components/XAssistant.jsx";
import { useAuth } from "./auth/AuthContext.jsx";

const NAV = [
  { to: "/", label: "Shop", icon: "⌂", roles: ["customer"] },
  { to: "/my-orders", label: "Orders", icon: "◎", roles: ["customer"] },
  { to: "/merchant", label: "Orders", icon: "◫", roles: ["partner"] },
  { to: "/partner", label: "Claims", icon: "◇", roles: ["partner"] },
  { to: "/rider", label: "Deliveries", icon: "➜", roles: ["rider"] },
  { to: "/ops", label: "Live ops", icon: "◈", roles: ["ops", "admin"] },
  { to: "/support", label: "Support", icon: "?", roles: ["support", "admin"] },
  { to: "/claims", label: "Claim risk", icon: "⚑", roles: ["support", "admin"] },
  { to: "/admin", label: "Admin", icon: "⚙", roles: ["admin"] },
];

const ROLE_LABELS = {
  customer: "Customer",
  ops: "Operations",
  partner: "Merchant",
  rider: "Rider",
  support: "Support",
  admin: "Administrator",
};

const navLinkClass = ({ isActive }) =>
  `group inline-flex items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-semibold transition ${
    isActive
      ? "bg-slate-950 text-white shadow-[0_8px_24px_-14px_rgba(15,23,42,.9)]"
      : "text-slate-500 hover:bg-white hover:text-slate-950"
  }`;

export default function App() {
  const { user, profile, role, signOut, loading } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const visibleNav = role ? NAV.filter((item) => item.roles.includes(role)) : [];
  const activeItem = NAV.find((item) => item.to === location.pathname && (!role || item.roles.includes(role)));

  return (
    <div className="app-surface min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 sm:px-6">
          <NavLink to="/" className="group flex shrink-0 items-center gap-2" onClick={() => setMobileOpen(false)}>
            <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-slate-950 text-base font-black text-white shadow-lg transition group-hover:-translate-y-0.5 group-hover:rotate-3">
              X
            </span>
            <span className="hidden leading-tight sm:block">
              <span className="block text-base font-black tracking-tight text-slate-950">ResolveX</span>
            </span>
          </NavLink>

          {!loading && user && role && (
            <nav className="ml-2 hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto lg:flex">
              {visibleNav.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                  <span className="text-xs opacity-70">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-2">
            {!loading && !user && (
              <>
                <NavLink to="/login" className="hidden rounded-xl px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-white hover:text-slate-950 sm:inline-flex">
                  Sign in
                </NavLink>
                <NavLink to="/signup" className="btn">Create account</NavLink>
              </>
            )}

            {!loading && user && (
              <>
                <div className="hidden items-center gap-2 rounded-2xl border border-slate-200/80 bg-white/80 px-3 py-1.5 shadow-sm sm:flex">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-teal-100 to-amber-50 text-xs font-black text-slate-900">
                    {(profile?.display_name || user.email || "U").slice(0, 1).toUpperCase()}
                  </div>
                  <div className="max-w-36 leading-tight">
                    <p className="truncate text-xs font-bold text-slate-900">{profile?.display_name || user.email}</p>
                    <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">{ROLE_LABELS[role] || role}</p>
                  </div>
                </div>
                <button className="btn-secondary hidden sm:inline-flex" onClick={signOut}>Sign out</button>
                <button
                  className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200 bg-white text-lg text-slate-700 shadow-sm lg:hidden"
                  onClick={() => setMobileOpen((open) => !open)}
                  aria-label="Toggle navigation"
                  aria-expanded={mobileOpen}
                >
                  {mobileOpen ? "×" : "≡"}
                </button>
              </>
            )}
          </div>
        </div>

        {!loading && user && role && mobileOpen && (
          <div className="border-t border-slate-100 bg-white/95 px-4 py-3 shadow-xl lg:hidden">
            <div className="mx-auto grid max-w-7xl grid-cols-2 gap-2 sm:grid-cols-3">
              {visibleNav.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass} onClick={() => setMobileOpen(false)}>
                  <span className="text-xs opacity-70">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
              <button className="btn-secondary" onClick={signOut}>Sign out</button>
            </div>
          </div>
        )}
      </header>

      {user && activeItem && location.pathname !== "/" && (
        <div className="border-b border-slate-200/60 bg-white/45 backdrop-blur">
          <div className="mx-auto max-w-7xl px-4 py-2 text-xs font-semibold text-slate-600 sm:px-6">
            {activeItem.label}
          </div>
        </div>
      )}

      <main className="flex-1 animate-fade-up">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Storefront />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/my-orders" element={<ProtectedRoute allowedRoles={["customer"]}><OrderDashboard key="customer" /></ProtectedRoute>} />
          <Route path="/report" element={<ProtectedRoute allowedRoles={["customer", "admin"]}><CustomerApp /></ProtectedRoute>} />
          <Route path="/merchant" element={<ProtectedRoute allowedRoles={["partner", "admin"]}><OrderDashboard key="merchant" mode="merchant" /></ProtectedRoute>} />
          <Route path="/rider" element={<ProtectedRoute allowedRoles={["rider", "admin"]}><OrderDashboard key="rider" mode="rider" /></ProtectedRoute>} />
          <Route path="/ops" element={<ProtectedRoute allowedRoles={["ops", "admin"]}><OpsDashboard /></ProtectedRoute>} />
          <Route path="/partner" element={<ProtectedRoute allowedRoles={["partner", "admin"]}><PartnerPortal /></ProtectedRoute>} />
          <Route path="/support" element={<ProtectedRoute allowedRoles={["support", "admin"]}><SupportQueue /></ProtectedRoute>} />
          <Route path="/claims" element={<ProtectedRoute allowedRoles={["admin", "support"]}><ClaimRiskBoard /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute allowedRoles={["admin"]}><Admin /></ProtectedRoute>} />
        </Routes>
      </main>

      <XAssistant />
    </div>
  );
}

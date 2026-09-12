import { NavLink, Route, Routes } from "react-router-dom";

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
import { useAuth } from "./auth/AuthContext.jsx";

const navLinkClass = ({ isActive }) =>
  `whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition ${
    isActive ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-white/80 hover:text-slate-900"
  }`;

const NAV = [
  { to: "/", label: "Shop", roles: ["customer", "admin"] },
  { to: "/my-orders", label: "My orders", roles: ["customer"] },
  { to: "/merchant", label: "Restaurant", roles: ["partner", "admin"] },
  { to: "/rider", label: "Deliveries", roles: ["rider", "admin"] },
  { to: "/ops", label: "Ops", roles: ["ops", "admin"] },
  { to: "/partner", label: "Partner", roles: ["partner", "admin"] },
  { to: "/support", label: "Support", roles: ["support", "admin"] },
  { to: "/claims", label: "Claim Risk", roles: ["support", "admin"] },
  { to: "/admin", label: "Admin", roles: ["admin"] },
];

export default function App() {
  const { user, profile, role, signOut, loading } = useAuth();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <NavLink to="/" className="shrink-0 text-lg font-bold tracking-tight text-slate-900">
            Resolve<span className="text-teal-700">X</span>
          </NavLink>
          <div className="flex min-w-0 items-center gap-3">
            {!loading && user && role && (
              <nav className="flex max-w-[58vw] items-center gap-1 overflow-x-auto sm:max-w-none">
                {NAV.filter((item) => item.roles.includes(role)).map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            )}
            {!loading && !user && (
              <div className="flex items-center gap-2">
                <NavLink to="/login" className="text-sm font-medium text-slate-600">Sign in</NavLink>
                <NavLink to="/signup" className="btn">Create account</NavLink>
              </div>
            )}
            {!loading && user && (
              <div className="flex items-center gap-3">
                <div className="hidden text-right leading-tight sm:block">
                  <p className="text-sm font-medium">{profile?.display_name || user.email}</p>
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">{role || "unassigned"}</p>
                </div>
                <button className="btn-secondary" onClick={signOut}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">
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
    </div>
  );
}

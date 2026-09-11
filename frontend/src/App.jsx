import { NavLink, Route, Routes } from "react-router-dom";

import CustomerApp from "./pages/CustomerApp.jsx";
import OpsDashboard from "./pages/OpsDashboard.jsx";
import PartnerPortal from "./pages/PartnerPortal.jsx";
import Admin from "./pages/Admin.jsx";
import SupportQueue from "./pages/SupportQueue.jsx";
import Login from "./pages/Login.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import { useAuth } from "./auth/AuthContext.jsx";

const navLinkClass = ({ isActive }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
  }`;

const NAV = [
  { to: "/", label: "Customer", roles: ["customer", "admin"] },
  { to: "/ops", label: "Ops Dashboard", roles: ["ops", "admin"] },
  { to: "/partner", label: "Partner Portal", roles: ["partner", "admin"] },
  { to: "/support", label: "Support Queue", roles: ["support", "admin"] },
  { to: "/admin", label: "Admin", roles: ["admin"] },
];

export default function App() {
  const { user, profile, role, signOut, loading } = useAuth();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <span className="font-bold text-lg">ResolveX</span>
          <div className="flex items-center gap-4">
            {!loading && user && role && (
              <nav className="hidden md:flex gap-2">
                {NAV.filter((item) => item.roles.includes(role)).map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            )}
            {!loading && user && (
              <div className="flex items-center gap-3">
                <div className="hidden sm:block text-right leading-tight">
                  <p className="text-sm font-medium">{profile?.display_name || user.email}</p>
                  <p className="text-xs uppercase text-slate-500">{role || "unassigned"}</p>
                </div>
                <button className="btn-secondary" onClick={signOut}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 bg-slate-50">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute allowedRoles={["customer", "admin"]}><CustomerApp /></ProtectedRoute>} />
          <Route path="/ops" element={<ProtectedRoute allowedRoles={["ops", "admin"]}><OpsDashboard /></ProtectedRoute>} />
          <Route path="/partner" element={<ProtectedRoute allowedRoles={["partner", "admin"]}><PartnerPortal /></ProtectedRoute>} />
          <Route path="/support" element={<ProtectedRoute allowedRoles={["support", "admin"]}><SupportQueue /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute allowedRoles={["admin"]}><Admin /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  );
}

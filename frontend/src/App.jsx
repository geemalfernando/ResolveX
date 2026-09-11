import { NavLink, Route, Routes } from "react-router-dom";

import ClaimRiskBoard from "./pages/ClaimRiskBoard.jsx";
import CustomerApp from "./pages/CustomerApp.jsx";
import OpsDashboard from "./pages/OpsDashboard.jsx";
import PartnerPortal from "./pages/PartnerPortal.jsx";
import Admin from "./pages/Admin.jsx";
import SupportQueue from "./pages/SupportQueue.jsx";

const navLinkClass = ({ isActive }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
  }`;

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <span className="font-bold text-lg">ResolveX</span>
          <nav className="flex gap-2 flex-wrap justify-end">
            <NavLink to="/" end className={navLinkClass}>
              Customer
            </NavLink>
            <NavLink to="/ops" className={navLinkClass}>
              Ops Dashboard
            </NavLink>
            <NavLink to="/claims" className={navLinkClass}>
              Claim Risk
            </NavLink>
            <NavLink to="/partner" className={navLinkClass}>
              Partner Portal
            </NavLink>
            <NavLink to="/support" className={navLinkClass}>
              Support Queue
            </NavLink>
            <NavLink to="/admin" className={navLinkClass}>Admin</NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1 bg-slate-50">
        <Routes>
          <Route path="/" element={<CustomerApp />} />
          <Route path="/ops" element={<OpsDashboard />} />
          <Route path="/claims" element={<ClaimRiskBoard />} />
          <Route path="/partner" element={<PartnerPortal />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/support" element={<SupportQueue />} />
        </Routes>
      </main>
    </div>
  );
}

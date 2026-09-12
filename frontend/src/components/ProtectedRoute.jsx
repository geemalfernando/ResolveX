import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const HOME_BY_ROLE = {
  customer: "/",
  ops: "/ops",
  partner: "/merchant",
  rider: "/rider",
  support: "/claims",
  admin: "/admin",
};

export default function ProtectedRoute({ allowedRoles, children }) {
  const { user, role, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="max-w-4xl mx-auto p-8 text-slate-600">Checking access…</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!role) {
    return (
      <div className="max-w-xl mx-auto p-8">
        <div className="rounded-xl border bg-white p-6">
          <h1 className="text-xl font-bold">Account role not assigned</h1>
          <p className="mt-2 text-slate-600">Your account is signed in, but it has not been assigned a ResolveX role yet.</p>
        </div>
      </div>
    );
  }

  if (!allowedRoles.includes(role)) {
    return <Navigate to={HOME_BY_ROLE[role] ?? "/login"} replace />;
  }

  return children;
}

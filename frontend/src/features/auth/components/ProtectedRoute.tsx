import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute() {
  const { currentUser, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <main className="session-check">
        <p>Checking recruiter session...</p>
      </main>
    );
  }

  if (!currentUser) {
    return <Navigate to="/recruiter/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

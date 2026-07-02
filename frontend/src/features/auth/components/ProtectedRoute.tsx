import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { fetchRecruiterAccount } from "../services/authService";

interface ProtectedRouteProps {
  requireSubscription?: boolean;
}

type AccountCheck = "idle" | "checking" | "active" | "pending" | "error";

export function ProtectedRoute({ requireSubscription = true }: ProtectedRouteProps) {
  const { currentUser, loading } = useAuth();
  const location = useLocation();
  const [accountCheck, setAccountCheck] = useState<AccountCheck>(
    requireSubscription ? "checking" : "idle",
  );
  const [accountError, setAccountError] = useState("");

  useEffect(() => {
    let active = true;
    if (!requireSubscription || !currentUser) {
      setAccountCheck("idle");
      return undefined;
    }

    setAccountCheck("checking");
    setAccountError("");
    void currentUser
      .getIdToken()
      .then(fetchRecruiterAccount)
      .then((account) => {
        if (active) {
          setAccountCheck(
            account.subscription_status === "free_trial" ? "active" : "pending",
          );
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setAccountError(
            error instanceof Error
              ? error.message
              : "Unable to validate your recruiter account.",
          );
          setAccountCheck("error");
        }
      });

    return () => {
      active = false;
    };
  }, [currentUser, requireSubscription]);

  if (loading || accountCheck === "checking") {
    return (
      <main className="session-check">
        <p>Checking recruiter session...</p>
      </main>
    );
  }

  if (!currentUser) {
    return <Navigate to="/recruiter/login" replace state={{ from: location }} />;
  }

  if (requireSubscription && accountCheck === "pending") {
    return <Navigate to="/recruiter/subscription" replace />;
  }

  if (requireSubscription && accountCheck === "error") {
    return (
      <main className="session-check session-check-error">
        <div>
          <h1>We couldn&apos;t prepare your account</h1>
          <p>{accountError}</p>
          <a href="/recruiter/login">Return to login</a>
        </div>
      </main>
    );
  }

  return <Outlet />;
}

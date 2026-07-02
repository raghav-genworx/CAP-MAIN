import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import {
  fetchRecruiterAccount,
  startFreeTrial,
  type RecruiterAccount,
} from "../services/authService";

export function RecruiterSubscriptionPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [account, setAccount] = useState<RecruiterAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadAccount() {
      if (!currentUser) {
        setLoading(false);
        return;
      }
      try {
        const result = await fetchRecruiterAccount(await currentUser.getIdToken());
        if (active) setAccount(result);
      } catch (loadError) {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to prepare your recruiter account.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadAccount();
    return () => {
      active = false;
    };
  }, [currentUser]);

  async function handleStartTrial() {
    if (!currentUser) return;
    setStarting(true);
    setError("");
    try {
      await startFreeTrial(await currentUser.getIdToken());
      navigate("/recruiter/dashboard", { replace: true });
    } catch (trialError) {
      setError(
        trialError instanceof Error
          ? trialError.message
          : "Unable to start your free trial.",
      );
      setStarting(false);
    }
  }

  if (loading) {
    return <main className="session-check">Preparing your account...</main>;
  }

  return (
    <main className="subscription-page">
      <section className="subscription-shell">
        <div className="subscription-copy">
          <p className="subscription-eyebrow">One last step</p>
          <h1>Start hiring with CAP</h1>
          <p>
            Your recruiter account is ready. Activate the free plan to enter your
            private assessment workspace.
          </p>
        </div>

        <article className="subscription-card">
          <div className="subscription-plan-heading">
            <div>
              <span>CAP Recruiter</span>
              <h2>Free Trial</h2>
            </div>
            <strong>FREE</strong>
          </div>

          <p className="subscription-price">
            ₹0 <span>to get started</span>
          </p>

          <ul>
            <li><Check size={18} /> Create coding assessments</li>
            <li><Check size={18} /> Manage questions and candidates</li>
            <li><Check size={18} /> View evaluations and reports</li>
            <li><Check size={18} /> Your data stays in your workspace</li>
          </ul>

          {error ? <div className="auth-error">{error}</div> : null}

          <button
            className="subscription-cta"
            type="button"
            disabled={starting || !account}
            onClick={() => void handleStartTrial()}
          >
            {starting
              ? "Starting your trial..."
              : account?.subscription_status === "free_trial"
                ? "Trial already active"
                : "Start free trial"}
          </button>
          <small>No card required.</small>
        </article>
      </section>
    </main>
  );
}

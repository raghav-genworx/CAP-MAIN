import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { GoogleLogo, MicrosoftLogo } from "./components/ProviderLogos";
import { SocialAuthButton } from "./components/SocialAuthButton";
import { useAuth } from "./hooks/useAuth";
import { getAuthErrorMessage } from "./utils/authErrors";

interface LocationState {
  from?: {
    pathname?: string;
  };
}

type LoadingState = "email" | "google" | "microsoft" | null;

export function RecruiterLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { loginWithEmail, signInWithGoogle, signInWithMicrosoft } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);

  const redirectTo =
    (location.state as LocationState | null)?.from?.pathname ||
    "/recruiter/dashboard";

  async function handleEmailLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading("email");

    try {
      await loginWithEmail(email, password);
      navigate(redirectTo, { replace: true });
    } catch (authError) {
      setError(getAuthErrorMessage(authError, "Unable to login. Please try again."));
    } finally {
      setLoading(null);
    }
  }

  async function handleProviderLogin(provider: "google" | "microsoft") {
    setError("");
    setLoading(provider);

    try {
      if (provider === "google") {
        await signInWithGoogle();
      } else {
        await signInWithMicrosoft();
      }

      navigate(redirectTo, { replace: true });
    } catch (authError) {
      setError(
        getAuthErrorMessage(authError, "Unable to complete provider sign-in."),
      );
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="auth-page auth-page-login">
      <section className="auth-panel-grid">
        <div className="auth-hero">
          <p className="auth-eyebrow">Recruiter Authentication</p>
          <h1>Hire faster with a secure assessment workspace.</h1>
          <p>
            Login to manage questions, prepare coding assessments, and keep
            recruiter workflows protected with Firebase Authentication.
          </p>
        </div>

        <div className="auth-form-card">
          <div className="auth-form-heading">
            <p>Recruiter Portal</p>
            <h2>Welcome back</h2>
            <span>Sign in to continue to your recruiter dashboard.</span>
          </div>

          {error ? <div className="auth-error">{error}</div> : null}

          <div className="auth-provider-grid">
            <SocialAuthButton
              icon={<GoogleLogo />}
              loading={loading === "google"}
              loadingText="Opening Google..."
              onClick={() => void handleProviderLogin("google")}
            >
              Continue with Google
            </SocialAuthButton>
            <SocialAuthButton
              icon={<MicrosoftLogo />}
              loading={loading === "microsoft"}
              loadingText="Opening Microsoft..."
              onClick={() => void handleProviderLogin("microsoft")}
            >
              Continue with Microsoft
            </SocialAuthButton>
          </div>

          <div className="auth-divider">
            <span />
            or use email
            <span />
          </div>

          <form className="auth-form" onSubmit={handleEmailLogin}>
            <label>
              <span>Email address</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                placeholder="recruiter@company.com"
                required
              />
            </label>

            <label>
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                placeholder="Enter your password"
                required
              />
            </label>

            <button className="auth-submit" type="submit" disabled={loading !== null}>
              {loading === "email" ? "Logging in..." : "Login with email"}
            </button>
          </form>

          <p className="auth-switch">Recruiter access is managed by the team.</p>
        </div>
      </section>
    </main>
  );
}

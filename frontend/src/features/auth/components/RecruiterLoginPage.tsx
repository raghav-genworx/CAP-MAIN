import { type FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { GoogleLogo, MicrosoftLogo } from "./ProviderLogos";
import { SocialAuthButton } from "./SocialAuthButton";
import { useAuth } from "../hooks/useAuth";
import {
  clearOAuthIntent,
  consumeOAuthError,
  consumeOAuthIntent,
  saveOAuthIntent,
} from "../utils/oauthIntent";
import { getAuthErrorMessage } from "../utils/authErrors";

interface LocationState {
  from?: {
    pathname?: string;
  };
  signupSuccess?: string;
  verificationSuccess?: string;
}

type LoadingState = "email" | "google" | "microsoft" | null;

export function RecruiterLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    currentUser,
    loading: authLoading,
    loginWithEmail,
    signInWithGoogle,
    signInWithMicrosoft,
  } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);
  const signupSuccess = (location.state as LocationState | null)?.signupSuccess;
  const verificationSuccess = (location.state as LocationState | null)
    ?.verificationSuccess;

  const redirectTo =
    (location.state as LocationState | null)?.from?.pathname ||
    "/recruiter/dashboard";

  useEffect(() => {
    if (authLoading) return;
    const redirectError = consumeOAuthError();
    if (redirectError) setError(redirectError);
  }, [authLoading]);

  useEffect(() => {
    if (!currentUser) return;
    const intent = consumeOAuthIntent();
    if (intent === "login") {
      navigate(redirectTo, { replace: true });
    }
  }, [currentUser, navigate, redirectTo]);

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
    saveOAuthIntent("login");

    try {
      if (provider === "google") {
        await signInWithGoogle();
      } else {
        await signInWithMicrosoft();
      }
    } catch (authError) {
      clearOAuthIntent();
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
        </div>

        <div className="auth-form-card">
          <div className="auth-form-heading">
            <p>Recruiter Portal</p>
            <h2>Welcome back</h2>
            <span>Sign in to continue to your recruiter dashboard.</span>
          </div>

          {error ? <div className="auth-error">{error}</div> : null}
          {signupSuccess ? <div className="auth-success">{signupSuccess}</div> : null}
          {verificationSuccess ? (
            <div className="auth-success">{verificationSuccess}</div>
          ) : null}

          <section className="auth-choice-section" aria-labelledby="provider-login-title">
            <h3 className="auth-section-title" id="provider-login-title">
              Continue with
            </h3>
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
          </section>

          <div className="auth-divider">
            <span />
            or
            <span />
          </div>

          <section className="auth-choice-section" aria-labelledby="email-login-title">
            <h3 className="auth-section-title" id="email-login-title">
              Sign in with email
            </h3>
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
          </section>

          <p className="auth-switch">
            New to CAP? <Link to="/recruiter/signup">Create an account</Link>
          </p>
        </div>
      </section>
    </main>
  );
}

import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

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

type LoadingState = "email" | "google" | "microsoft" | null;

export function RecruiterSignupPage() {
  const navigate = useNavigate();
  const {
    currentUser,
    loading: authLoading,
    signupWithEmail,
    signInWithGoogle,
    signInWithMicrosoft,
  } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);

  useEffect(() => {
    if (authLoading) return;
    const redirectError = consumeOAuthError();
    if (redirectError) setError(redirectError);
  }, [authLoading]);

  useEffect(() => {
    if (!currentUser) return;
    const intent = consumeOAuthIntent();
    if (intent === "signup") {
      navigate("/recruiter/subscription", { replace: true });
    }
  }, [currentUser, navigate]);

  async function handleEmailSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading("email");

    try {
      await signupWithEmail(email, password);
      navigate("/recruiter/login", {
        replace: true,
        state: {
          signupSuccess:
            "Verification link sent. Verify your email, then log in to continue.",
        },
      });
    } catch (authError) {
      setError(
        getAuthErrorMessage(authError, "Unable to create your recruiter account."),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleProviderSignup(provider: "google" | "microsoft") {
    setError("");
    setLoading(provider);
    saveOAuthIntent("signup");

    try {
      if (provider === "google") {
        await signInWithGoogle();
      } else {
        await signInWithMicrosoft();
      }
    } catch (authError) {
      clearOAuthIntent();
      setError(
        getAuthErrorMessage(authError, "Unable to complete provider sign-up."),
      );
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="auth-page auth-page-signup">
      <section className="auth-panel-grid">
        <div className="auth-hero">
          <p className="auth-eyebrow">CAP Workspace</p>
          <h1>Create recruiter access</h1>
          <p>Set up secure access for assessment and question workflows.</p>
        </div>

        <div className="auth-form-card">
          <div className="auth-form-heading">
            <p>Recruiter Portal</p>
            <h2>Create your account</h2>
            <span>Sign up to start managing assessments and question workflows.</span>
          </div>

          {error ? <div className="auth-error">{error}</div> : null}

          <div className="auth-provider-grid">
            <SocialAuthButton
              icon={<GoogleLogo />}
              loading={loading === "google"}
              loadingText="Opening Google..."
              onClick={() => void handleProviderSignup("google")}
            >
              Sign up with Google
            </SocialAuthButton>
            <SocialAuthButton
              icon={<MicrosoftLogo />}
              loading={loading === "microsoft"}
              loadingText="Opening Microsoft..."
              onClick={() => void handleProviderSignup("microsoft")}
            >
              Sign up with Microsoft
            </SocialAuthButton>
          </div>

          <div className="auth-divider">
            <span />
            or use email
            <span />
          </div>

          <form className="auth-form" onSubmit={handleEmailSignup}>
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
                autoComplete="new-password"
                minLength={6}
                placeholder="Create a password"
                required
              />
            </label>

            <label>
              <span>Confirm password</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                autoComplete="new-password"
                minLength={6}
                placeholder="Confirm your password"
                required
              />
            </label>

            <button className="auth-submit" type="submit" disabled={loading !== null}>
              {loading === "email" ? "Creating account..." : "Create recruiter account"}
            </button>
          </form>

          <p className="auth-switch">
            Already have an account? <Link to="/recruiter/login">Login</Link>
          </p>
        </div>
      </section>
    </main>
  );
}

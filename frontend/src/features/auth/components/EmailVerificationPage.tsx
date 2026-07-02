import { applyActionCode } from "firebase/auth";
import { CheckCircle2, CircleAlert, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { assertFirebaseAuth } from "../../../lib/firebase";
import { getAuthErrorMessage } from "../utils/authErrors";

type VerificationState = "verifying" | "success" | "error";

const verificationRequests = new Map<string, Promise<void>>();

function verifyEmailAction(actionCode: string): Promise<void> {
  const existing = verificationRequests.get(actionCode);
  if (existing) return existing;

  const request = applyActionCode(assertFirebaseAuth(), actionCode);
  verificationRequests.set(actionCode, request);
  return request;
}

export function EmailVerificationPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [state, setState] = useState<VerificationState>("verifying");
  const [error, setError] = useState("");

  const mode = searchParams.get("mode");
  const actionCode = searchParams.get("oobCode") ?? "";

  useEffect(() => {
    let active = true;
    let redirectTimer: ReturnType<typeof setTimeout> | undefined;

    if (mode !== "verifyEmail" || !actionCode) {
      setState("error");
      setError("This email verification link is incomplete or invalid.");
      return undefined;
    }

    void verifyEmailAction(actionCode)
      .then(() => {
        if (!active) return;
        setState("success");
        redirectTimer = setTimeout(() => {
          navigate("/recruiter/login", {
            replace: true,
            state: {
              verificationSuccess:
                "Email verified successfully. You can now log in.",
            },
          });
        }, 2200);
      })
      .catch((verificationError: unknown) => {
        if (!active) return;
        setState("error");
        setError(
          getAuthErrorMessage(
            verificationError,
            "This verification link is invalid or has expired.",
          ),
        );
      });

    return () => {
      active = false;
      if (redirectTimer) clearTimeout(redirectTimer);
    };
  }, [actionCode, mode, navigate]);

  return (
    <main className="auth-page verification-page">
      <section className="verification-card">
        {state === "verifying" ? (
          <>
            <LoaderCircle className="verification-spinner" size={44} />
            <h1>Verifying your email</h1>
            <p>Please wait while Firebase confirms your verification link.</p>
          </>
        ) : null}

        {state === "success" ? (
          <>
            <CheckCircle2 className="verification-success-icon" size={48} />
            <h1>Email verified successfully</h1>
            <p>Your account is ready. Redirecting you to Login...</p>
          </>
        ) : null}

        {state === "error" ? (
          <>
            <CircleAlert className="verification-error-icon" size={48} />
            <h1>Verification unsuccessful</h1>
            <p>{error}</p>
            <Link to="/recruiter/login">Return to Login</Link>
          </>
        ) : null}
      </section>
    </main>
  );
}

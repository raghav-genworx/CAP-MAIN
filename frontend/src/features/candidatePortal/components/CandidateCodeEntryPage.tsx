import { type FormEvent, useState } from "react";
import { ArrowRight, KeyRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";

export function CandidateCodeEntryPage() {
  const navigate = useNavigate();
  const [assessmentCode, setAssessmentCode] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = assessmentCode.trim();

    if (!code) {
      setError("Enter your assessment code.");
      return;
    }

    navigate(`/candidate/invite/${encodeURIComponent(code)}`);
  }

  return (
    <main className="candidate-shell candidate-shell-branded">
      <Card className="candidate-card candidate-code-card">
        <span className="candidate-kicker">Candidate Access</span>
        <h1>Enter assessment code</h1>
        <p className="candidate-muted">
          Use the code shared by your recruiter to open the assessment lobby.
        </p>

        <form className="candidate-code-form" onSubmit={handleSubmit}>
          <label>
            <span>Assessment code</span>
            <div className="candidate-code-input">
              <KeyRound size={18} aria-hidden="true" />
              <input
                type="text"
                value={assessmentCode}
                onChange={(event) => {
                  setAssessmentCode(event.target.value);
                  setError("");
                }}
                autoComplete="one-time-code"
                placeholder="CAP-INVITE-CODE"
              />
            </div>
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <Button type="submit">
            Continue
            <ArrowRight size={17} aria-hidden="true" />
          </Button>
        </form>
      </Card>
    </main>
  );
}

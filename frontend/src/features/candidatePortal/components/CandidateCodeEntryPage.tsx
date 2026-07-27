import { type FormEvent, useRef, useState } from "react";
import { ArrowRight, LoaderCircle, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { CandidatePageShell } from "./CandidatePageShell";

const CODE_FIELD_ID = "candidate-assessment-code";
const CODE_HINT_ID = "candidate-assessment-code-hint";
const CODE_ERROR_ID = "candidate-assessment-code-error";

export function CandidateCodeEntryPage() {
  const navigate = useNavigate();
  const [assessmentCode, setAssessmentCode] = useState("");
  const [error, setError] = useState("");
  const [isOpening, setIsOpening] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = assessmentCode.trim();

    if (!code) {
      setError("Enter the assessment code from your invitation email.");
      inputRef.current?.focus();
      return;
    }

    setError("");
    setIsOpening(true);
    navigate(`/candidate/invite/${encodeURIComponent(code)}`);
  }

  return (
    <CandidatePageShell>
      <Card className="cap-panel cap-panel-narrow" aria-labelledby="cap-code-entry-title">
        <div className="cap-panel-intro">
          <h1 id="cap-code-entry-title">Enter your assessment code</h1>
          <p>
            Your recruiter sends this code in your invitation email, together with
            the assessment link. Entering it opens your assessment lobby, where you
            can review the details before you begin.
          </p>
        </div>

        <form className="cap-form" onSubmit={handleSubmit} noValidate>
          <div className="cap-field">
            <label htmlFor={CODE_FIELD_ID}>Assessment code</label>
            <input
              id={CODE_FIELD_ID}
              ref={inputRef}
              type="text"
              inputMode="text"
              spellCheck={false}
              autoComplete="one-time-code"
              autoCapitalize="characters"
              className={`cap-input cap-input-code ${error ? "is-invalid" : ""}`}
              placeholder="e.g. CAP-4KQ7-2ZDX"
              value={assessmentCode}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${CODE_HINT_ID} ${CODE_ERROR_ID}` : CODE_HINT_ID}
              disabled={isOpening}
              onChange={(event) => {
                setAssessmentCode(event.target.value);
                if (error) {
                  setError("");
                }
              }}
            />
            <p className="cap-field-hint" id={CODE_HINT_ID}>
              Codes are not case sensitive. Copy and paste is fine.
            </p>
            <p className="cap-field-error" id={CODE_ERROR_ID} role="alert">
              {error}
            </p>
          </div>

          <Button type="submit" className="cap-btn cap-btn-block" disabled={isOpening}>
            {isOpening ? (
              <>
                <LoaderCircle size={16} className="cap-spin" aria-hidden="true" />
                Opening assessment lobby…
              </>
            ) : (
              <>
                Continue
                <ArrowRight size={16} aria-hidden="true" />
              </>
            )}
          </Button>
          <p className="cap-live-note" role="status">
            {isOpening ? "Opening your assessment lobby." : ""}
          </p>
        </form>

        <p className="cap-note">
          <ShieldCheck size={15} aria-hidden="true" />
          <span>
            Only use a code issued directly to you. Nothing is submitted on this
            page — you will see the assessment details before anything starts.
          </span>
        </p>
      </Card>
    </CandidatePageShell>
  );
}

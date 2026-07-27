import Editor from "@monaco-editor/react";
import { CheckCircle2, ChevronRight, Play, Save } from "lucide-react";

import { Button } from "../../../../components/ui/Button";
import { CandidateStatusIndicator } from "./CandidateStatusIndicator";
import type { SaveState } from "./types";
import type { CandidateQuestion } from "../../types/CandidatePortal";

const LANGUAGE_ALIASES: Record<string, string> = {
  "c++": "cpp",
  cplusplus: "cpp",
  cpp: "cpp",
  c: "c",
  csharp: "csharp",
  "c#": "csharp",
  java: "java",
  javascript: "javascript",
  js: "javascript",
  python: "python",
  python3: "python",
  py: "python",
  typescript: "typescript",
  ts: "typescript",
};

function monacoLanguage(language: string) {
  const normalized = language.trim().toLowerCase();
  return LANGUAGE_ALIASES[normalized] || normalized || "plaintext";
}

interface CandidateEditorPanelProps {
  question: CandidateQuestion;
  language: string;
  sourceCode: string;
  saveState: SaveState;
  isSubmitted: boolean;
  isPaused: boolean;
  isSaving: boolean;
  isRunningSample: boolean;
  isCheckingHidden: boolean;
  actionsDisabled: boolean;
  hiddenCooldownSeconds: number;
  hiddenAttemptsRemaining: number | null;
  nextQuestionTitle: string | null;
  onLanguageChange: (language: string) => void;
  onCodeChange: (sourceCode: string) => void;
  onSave: () => void;
  onRunSample: () => void;
  onSubmitQuestion: () => void;
  onNextQuestion: () => void;
}

export function CandidateEditorPanel({
  question,
  language,
  sourceCode,
  saveState,
  isSubmitted,
  isPaused,
  isSaving,
  isRunningSample,
  isCheckingHidden,
  actionsDisabled,
  hiddenCooldownSeconds,
  hiddenAttemptsRemaining,
  nextQuestionTitle,
  onLanguageChange,
  onCodeChange,
  onSave,
  onRunSample,
  onSubmitQuestion,
  onNextQuestion,
}: CandidateEditorPanelProps) {
  const hasCode = sourceCode.trim().length > 0;
  const editorLabel = `Code editor for question ${question.question_order}, ${question.title}`;
  const noAttemptsLeft = hiddenAttemptsRemaining === 0;

  return (
    <section className="cap-editor" aria-label="Solution editor">
      <div className="cap-editor-head">
        <div className="cap-editor-head-main">
          <h2>Your solution</h2>
          <CandidateStatusIndicator state={saveState} />
        </div>
        <div className="cap-field cap-field-inline">
          <label htmlFor="cap-language-select">Language</label>
          <select
            id="cap-language-select"
            className="cap-select"
            value={language}
            disabled={isPaused}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            {question.supported_languages.map((supported) => (
              <option key={supported} value={supported}>
                {supported}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isSubmitted ? (
        <p className="cap-editor-note" role="status">
          <CheckCircle2 size={15} aria-hidden="true" />
          <span>
            This question is submitted. You can keep editing and submit it again
            until you finish the assessment.
          </span>
        </p>
      ) : null}

      <div className="cap-monaco">
        <Editor
          height="100%"
          language={monacoLanguage(language)}
          theme="vs-dark"
          value={sourceCode}
          loading={<p className="cap-monaco-loading">Loading editor…</p>}
          options={{
            ariaLabel: editorLabel,
            accessibilitySupport: "auto",
            automaticLayout: true,
            fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
            fontSize: 14,
            minimap: { enabled: false },
            padding: { top: 16, bottom: 16 },
            readOnly: isPaused,
            renderLineHighlight: "line",
            scrollBeyondLastLine: false,
            smoothScrolling: false,
            tabSize: 2,
            wordWrap: "on",
          }}
          onChange={(value) => onCodeChange(value || "")}
        />
      </div>

      <div className="cap-editor-actions" role="group" aria-label="Solution actions">
        <p className="cap-action-hint">
          <strong>Save</strong> stores your progress. <strong>Run sample tests</strong>{" "}
          checks the visible examples. <strong>Submit question</strong> runs the
          hidden tests for this question — it does not finish the assessment.
        </p>
        <div className="cap-action-buttons">
          <Button
            type="button"
            variant="secondary"
            className="cap-btn cap-btn-sm"
            onClick={onSave}
            disabled={isSaving || isPaused}
          >
            <Save size={15} aria-hidden="true" />
            {isSaving ? "Saving…" : "Save"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="cap-btn cap-btn-sm"
            onClick={onRunSample}
            disabled={actionsDisabled || !hasCode}
          >
            <Play size={15} aria-hidden="true" />
            {isRunningSample ? "Running…" : "Run sample tests"}
          </Button>
          <Button
            type="button"
            className="cap-btn cap-btn-sm"
            onClick={onSubmitQuestion}
            disabled={
              actionsDisabled || !hasCode || hiddenCooldownSeconds > 0 || noAttemptsLeft
            }
          >
            <CheckCircle2 size={15} aria-hidden="true" />
            {isCheckingHidden
              ? "Checking…"
              : hiddenCooldownSeconds > 0
                ? `Submit again in ${hiddenCooldownSeconds}s`
                : "Submit question"}
          </Button>
          {isSubmitted && nextQuestionTitle ? (
            <Button
              type="button"
              variant="secondary"
              className="cap-btn cap-btn-sm"
              onClick={onNextQuestion}
            >
              Next question
              <ChevronRight size={15} aria-hidden="true" />
            </Button>
          ) : null}
        </div>
        {noAttemptsLeft ? (
          <p className="cap-action-note" role="status">
            You have used all available submission checks for this question. Your
            latest saved code is still included when you finish the assessment.
          </p>
        ) : hiddenAttemptsRemaining !== null && hiddenAttemptsRemaining > 0 ? (
          <p className="cap-action-note" role="status">
            {hiddenAttemptsRemaining} submission check
            {hiddenAttemptsRemaining === 1 ? "" : "s"} remaining for this question.
          </p>
        ) : null}
      </div>
    </section>
  );
}

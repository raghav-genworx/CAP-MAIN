import { Check, CircleDashed, CircleDot, CircleAlert } from "lucide-react";
import type { ComponentType } from "react";

import {
  QUESTION_STATUS_LABEL,
  type QuestionProgress,
  type QuestionProgressStatus,
} from "./types";

const STATUS_ICON: Record<QuestionProgressStatus, ComponentType<{ size?: number }>> = {
  not_started: CircleDashed,
  in_progress: CircleDot,
  submitted: Check,
  passed: Check,
  needs_attention: CircleAlert,
};

const LEGEND: QuestionProgressStatus[] = [
  "not_started",
  "in_progress",
  "submitted",
  "passed",
  "needs_attention",
];

interface CandidateQuestionNavigatorProps {
  items: QuestionProgress[];
  selectedQuestionId: string;
  onSelect: (questionId: string) => void;
}

export function CandidateQuestionNavigator({
  items,
  selectedQuestionId,
  onSelect,
}: CandidateQuestionNavigatorProps) {
  return (
    <nav className="cap-nav" aria-label="Assessment questions">
      <h2 className="cap-nav-title" id="cap-nav-title">
        Questions
      </h2>
      <ul className="cap-nav-list" aria-labelledby="cap-nav-title">
        {items.map((item) => {
          const Icon = STATUS_ICON[item.status];
          const isSelected = item.question.id === selectedQuestionId;
          return (
            <li key={item.question.id}>
              <button
                type="button"
                className={`cap-nav-item is-${item.status} ${isSelected ? "is-selected" : ""}`}
                aria-current={isSelected ? "true" : undefined}
                onClick={() => onSelect(item.question.id)}
              >
                <span className="cap-nav-index" aria-hidden="true">
                  {item.question.question_order}
                </span>
                <span className="cap-nav-body">
                  <span className="cap-nav-heading">
                    <span className="sr-only">
                      Question {item.question.question_order}:{" "}
                    </span>
                    {item.question.title}
                  </span>
                  <span className="cap-nav-status">
                    <Icon size={12} />
                    {QUESTION_STATUS_LABEL[item.status]}
                    {item.question.is_mandatory ? " · Required" : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="cap-nav-legend">
        <p className="cap-nav-legend-title">Status key</p>
        <ul>
          {LEGEND.map((status) => {
            const Icon = STATUS_ICON[status];
            return (
              <li key={status} className={`is-${status}`}>
                <Icon size={12} />
                {QUESTION_STATUS_LABEL[status]}
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

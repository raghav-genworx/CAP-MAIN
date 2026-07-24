import { useEffect, useState } from "react";

import { addMinutesToLocalInput } from "../utils/recruiterAssessmentViewModel";

const TIME_STEP_MINUTES = 5;

function roundedMinimum(value: string) {
  if (!value) {
    return value;
  }
  const minute = Number(value.slice(14, 16));
  const remainder = minute % TIME_STEP_MINUTES;
  return remainder
    ? addMinutesToLocalInput(value, TIME_STEP_MINUTES - remainder)
    : value.slice(0, 16);
}

function timeOptions(selectedTime: string) {
  const options = Array.from(
    { length: (24 * 60) / TIME_STEP_MINUTES },
    (_, index) => {
      const totalMinutes = index * TIME_STEP_MINUTES;
      const hour = String(Math.floor(totalMinutes / 60)).padStart(2, "0");
      const minute = String(totalMinutes % 60).padStart(2, "0");
      return `${hour}:${minute}`;
    },
  );
  if (selectedTime && !options.includes(selectedTime)) {
    options.push(selectedTime);
    options.sort();
  }
  return options;
}

export function FutureDateTimeField({
  label,
  value,
  minimum,
  onChange,
}: {
  label: string;
  value: string;
  minimum?: string;
  onChange: (value: string) => void;
}) {
  const effectiveMinimum = minimum ? roundedMinimum(minimum) : "";
  const minimumDate = effectiveMinimum.slice(0, 10);
  const selectedDate = value.slice(0, 10);
  const selectedTime = value.slice(11, 16);
  const displayedDate = selectedDate || minimumDate;

  function updateDate(date: string) {
    if (!date) {
      onChange("");
      return;
    }
    let time = selectedTime || (date === minimumDate ? effectiveMinimum.slice(11, 16) : "09:00");
    if (effectiveMinimum && `${date}T${time}` < effectiveMinimum) {
      time = effectiveMinimum.slice(11, 16);
    }
    onChange(`${date}T${time}`);
  }

  return (
    <div className="field future-date-time-field">
      <span>{label}</span>
      <div className="future-date-time-control">
        <label>
          <small>Date</small>
          <input
            type="date"
            min={minimumDate || undefined}
            value={selectedDate}
            onChange={(event) => updateDate(event.target.value)}
          />
        </label>
        <label>
          <small>Time</small>
          <select
            aria-label={`${label} time`}
            disabled={!displayedDate}
            value={selectedTime}
            onChange={(event) => onChange(`${displayedDate}T${event.target.value}`)}
          >
            {!selectedTime ? <option value="">Select time</option> : null}
            {timeOptions(selectedTime).map((time) => {
              const unavailable =
                Boolean(effectiveMinimum) &&
                `${displayedDate}T${time}` < effectiveMinimum;
              return (
                <option key={time} value={time} disabled={unavailable}>
                  {time}
                </option>
              );
            })}
          </select>
        </label>
      </div>
    </div>
  );
}

export function DurationMinutesField({
  label = "Duration (minutes)",
  value,
  minimum = 15,
  maximum = 360,
  onChange,
}: {
  label?: string;
  value: number;
  minimum?: number;
  maximum?: number;
  onChange: (value: number) => void;
}) {
  const [draft, setDraft] = useState(() => String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  function commitDraft() {
    const parsed = Number(draft);
    const normalized =
      Number.isFinite(parsed) && draft.trim() ? Math.round(parsed) : minimum;
    const nextValue = Math.min(
      maximum,
      Math.max(minimum, normalized),
    );
    setDraft(String(nextValue));
    onChange(nextValue);
  }

  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={minimum}
        max={maximum}
        inputMode="numeric"
        value={draft}
        onChange={(event) => {
          const nextDraft = event.target.value;
          setDraft(nextDraft);
          if (!nextDraft.trim()) {
            return;
          }
          const parsed = Number(nextDraft);
          if (Number.isFinite(parsed)) {
            onChange(parsed);
          }
        }}
        onBlur={commitDraft}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
      />
    </label>
  );
}

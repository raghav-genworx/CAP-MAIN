import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Clock3 } from "lucide-react";

import {
  formatSlotDateTimeLabel,
  isLocalInputBefore,
  splitLocalDateTimeInput,
} from "../../features/assessments/utils/recruiterAssessmentViewModel";

interface ScheduleDateTimePickerProps {
  label: string;
  value: string;
  min: string;
  onChange: (value: string) => void;
  error?: string;
  placeholder?: string;
  disabled?: boolean;
}

type Meridiem = "AM" | "PM";

type WheelTime = {
  hour12: number;
  minute: number;
  period: Meridiem;
};

const WHEEL_ITEM_HEIGHT = 36;
const HOURS_12 = Array.from({ length: 12 }, (_, index) => index + 1);
const MINUTES = Array.from({ length: 60 }, (_, index) => index);
const PERIODS: Meridiem[] = ["AM", "PM"];

function toTime24(hour12: number, minute: number, period: Meridiem) {
  let hour24 = hour12 % 12;
  if (period === "PM") {
    hour24 += 12;
  }
  return `${String(hour24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function parseTime24(time: string): WheelTime {
  const [hourValue = 0, minuteValue = 0] = time.split(":").map(Number);
  const period: Meridiem = hourValue >= 12 ? "PM" : "AM";
  const hour12 = hourValue % 12 || 12;
  return {
    hour12,
    minute: minuteValue,
    period,
  };
}

function composeDateTime(date: string, time: WheelTime) {
  return `${date}T${toTime24(time.hour12, time.minute, time.period)}`;
}

function isScheduleTimeAllowed(date: string, time: WheelTime, minimum: string) {
  if (!date) {
    return false;
  }
  return !isLocalInputBefore(composeDateTime(date, time), minimum);
}

function firstAllowedWheelTime(date: string, minimum: string): WheelTime | null {
  for (const period of PERIODS) {
    for (const hour12 of HOURS_12) {
      for (const minute of MINUTES) {
        const candidate = { hour12, minute, period };
        if (isScheduleTimeAllowed(date, candidate, minimum)) {
          return candidate;
        }
      }
    }
  }
  return null;
}

function timeToMinutes(time: WheelTime) {
  const [hour24, minute] = toTime24(time.hour12, time.minute, time.period)
    .split(":")
    .map(Number);
  return hour24 * 60 + minute;
}

function nearestAllowedWheelTime(
  date: string,
  preferred: WheelTime,
  minimum: string,
): WheelTime | null {
  const candidates: WheelTime[] = [];

  for (const period of PERIODS) {
    for (const hour12 of HOURS_12) {
      for (const minute of MINUTES) {
        const candidate = { hour12, minute, period };
        if (isScheduleTimeAllowed(date, candidate, minimum)) {
          candidates.push(candidate);
        }
      }
    }
  }

  if (!candidates.length) {
    return null;
  }

  const preferredMinutes = timeToMinutes(preferred);
  return candidates.reduce((best, candidate) => {
    const bestDistance = Math.abs(timeToMinutes(best) - preferredMinutes);
    const candidateDistance = Math.abs(timeToMinutes(candidate) - preferredMinutes);
    return candidateDistance < bestDistance ? candidate : best;
  });
}

function formatHour(hour12: number) {
  return String(hour12);
}

function formatMinute(minute: number) {
  return String(minute).padStart(2, "0");
}

function WheelColumn<T extends string | number>({
  items,
  value,
  onChange,
  formatValue,
  isDisabled,
}: {
  items: readonly T[];
  value: T;
  onChange: (value: T) => void;
  formatValue: (value: T) => string;
  isDisabled?: (value: T) => boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const scrollFrameRef = useRef<number | null>(null);

  const scrollToValue = useCallback(
    (target: T, behavior: ScrollBehavior = "auto") => {
      const index = items.indexOf(target);
      if (index < 0 || !listRef.current) {
        return;
      }
      listRef.current.scrollTo({
        top: index * WHEEL_ITEM_HEIGHT,
        behavior,
      });
    },
    [items],
  );

  useEffect(() => {
    scrollToValue(value, "auto");
  }, [scrollToValue, value]);

  const settleSelection = useCallback(() => {
    const list = listRef.current;
    if (!list) {
      return;
    }

    const rawIndex = Math.round(list.scrollTop / WHEEL_ITEM_HEIGHT);
    const clampedIndex = Math.max(0, Math.min(items.length - 1, rawIndex));

    let targetIndex = clampedIndex;
    if (isDisabled?.(items[targetIndex])) {
      let offset = 1;
      while (offset < items.length) {
        const before = clampedIndex - offset;
        const after = clampedIndex + offset;
        if (before >= 0 && !isDisabled(items[before])) {
          targetIndex = before;
          break;
        }
        if (after < items.length && !isDisabled(items[after])) {
          targetIndex = after;
          break;
        }
        offset += 1;
      }
    }

    const nextValue = items[targetIndex];
    if (nextValue !== undefined && nextValue !== value) {
      onChange(nextValue);
      return;
    }

    scrollToValue(nextValue ?? value, "smooth");
  }, [isDisabled, items, onChange, scrollToValue, value]);

  const handleScroll = () => {
    if (scrollFrameRef.current !== null) {
      window.clearTimeout(scrollFrameRef.current);
    }
    scrollFrameRef.current = window.setTimeout(() => {
      settleSelection();
      scrollFrameRef.current = null;
    }, 90);
  };

  return (
    <div className="schedule-time-wheel-column">
      <div
        ref={listRef}
        className="schedule-time-wheel-list"
        onScroll={handleScroll}
      >
        <div className="schedule-time-wheel-spacer" aria-hidden="true" />
        {items.map((item) => {
          const disabled = isDisabled?.(item) ?? false;
          const selected = item === value;
          return (
            <button
              key={String(item)}
              type="button"
              className={[
                "schedule-time-wheel-item",
                selected ? "is-selected" : "",
                disabled ? "is-disabled" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={disabled}
              onClick={() => {
                if (!disabled) {
                  onChange(item);
                  scrollToValue(item, "smooth");
                }
              }}
            >
              {formatValue(item)}
            </button>
          );
        })}
        <div className="schedule-time-wheel-spacer" aria-hidden="true" />
      </div>
    </div>
  );
}

export function ScheduleDateTimePicker({
  label,
  value,
  min,
  onChange,
  error,
  placeholder = "Select time",
  disabled = false,
}: ScheduleDateTimePickerProps) {
  const pickerId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [draftDate, setDraftDate] = useState("");
  const [draftTime, setDraftTime] = useState<WheelTime>({
    hour12: 9,
    minute: 0,
    period: "AM",
  });

  const minDate = splitLocalDateTimeInput(min).date || "";
  const draftValue = draftDate ? composeDateTime(draftDate, draftTime) : "";
  const canApply =
    Boolean(draftDate) && isScheduleTimeAllowed(draftDate, draftTime, min);

  const isHourDisabled = useCallback(
    (hour12: number) =>
      !PERIODS.some((period) =>
        MINUTES.some((minute) =>
          isScheduleTimeAllowed(draftDate, { hour12, minute, period }, min),
        ),
      ),
    [draftDate, min],
  );

  const isMinuteDisabled = useCallback(
    (minute: number) =>
      !isScheduleTimeAllowed(
        draftDate,
        { hour12: draftTime.hour12, minute, period: draftTime.period },
        min,
      ),
    [draftDate, draftTime.hour12, draftTime.period, min],
  );

  const isPeriodDisabled = useCallback(
    (period: Meridiem) =>
      !MINUTES.some((minute) =>
        isScheduleTimeAllowed(
          draftDate,
          { hour12: draftTime.hour12, minute, period },
          min,
        ),
      ),
    [draftDate, draftTime.hour12, min],
  );

  const resolvedDraftTime = useMemo(() => {
    if (!draftDate) {
      return draftTime;
    }
    if (isScheduleTimeAllowed(draftDate, draftTime, min)) {
      return draftTime;
    }
    return nearestAllowedWheelTime(draftDate, draftTime, min) ?? draftTime;
  }, [draftDate, draftTime, min]);

  useEffect(() => {
    if (
      resolvedDraftTime.hour12 !== draftTime.hour12 ||
      resolvedDraftTime.minute !== draftTime.minute ||
      resolvedDraftTime.period !== draftTime.period
    ) {
      setDraftTime(resolvedDraftTime);
    }
  }, [draftTime, resolvedDraftTime]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const { date: datePart, time: timePart } = splitLocalDateTimeInput(value || min);
    const nextDate = datePart || minDate;
    const preferred = timePart
      ? parseTime24(timePart)
      : firstAllowedWheelTime(nextDate, min) ?? draftTime;
    const resolved =
      nearestAllowedWheelTime(nextDate, preferred, min) ??
      firstAllowedWheelTime(nextDate, min) ??
      preferred;

    setDraftDate(nextDate);
    setDraftTime(resolved);
  }, [min, minDate, open, value]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  function applySelection() {
    if (!canApply || !draftValue) {
      return;
    }
    onChange(draftValue);
    setOpen(false);
  }

  return (
    <div
      ref={rootRef}
      className={`schedule-datetime-picker${open ? " is-open" : ""}${
        error ? " has-error" : ""
      }`}
    >
      <span className="schedule-datetime-label" id={`${pickerId}-label`}>
        {label}
      </span>
      <button
        type="button"
        className="schedule-datetime-trigger"
        aria-labelledby={`${pickerId}-label`}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{value ? formatSlotDateTimeLabel(value) : placeholder}</span>
        <Clock3 size={16} aria-hidden="true" />
      </button>
      {error ? (
        <p className="schedule-datetime-error" role="alert">
          {error}
        </p>
      ) : null}
      {open ? (
        <div
          className="schedule-datetime-popover"
          role="dialog"
          aria-label={`${label} picker`}
        >
          <label className="schedule-datetime-date-field">
            <span>Date</span>
            <input
              type="date"
              min={minDate}
              value={draftDate}
              onChange={(event) => setDraftDate(event.target.value)}
            />
          </label>

          <div className="schedule-time-wheel-panel">
            <div className="schedule-time-wheel-highlight" aria-hidden="true" />
            <WheelColumn
              items={HOURS_12}
              value={draftTime.hour12}
              formatValue={formatHour}
              isDisabled={isHourDisabled}
              onChange={(hour12) =>
                setDraftTime((current) => ({ ...current, hour12 }))
              }
            />
            <WheelColumn
              items={MINUTES}
              value={draftTime.minute}
              formatValue={formatMinute}
              isDisabled={isMinuteDisabled}
              onChange={(minute) =>
                setDraftTime((current) => ({ ...current, minute }))
              }
            />
            <WheelColumn
              items={PERIODS}
              value={draftTime.period}
              formatValue={(period) => period}
              isDisabled={isPeriodDisabled}
              onChange={(period) =>
                setDraftTime((current) => ({ ...current, period }))
              }
            />
          </div>

          <div className="schedule-datetime-actions">
            <button
              type="button"
              className="schedule-datetime-text-action"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="schedule-datetime-text-action is-primary"
              onClick={applySelection}
              disabled={!canApply}
            >
              OK
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

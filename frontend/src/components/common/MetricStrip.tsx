import type { ReactNode } from "react";

interface MetricItem {
  icon?: ReactNode;
  label: string;
  value: string | number;
}

interface MetricStripProps {
  items: MetricItem[];
}

export function MetricStrip({ items }: MetricStripProps) {
  return (
    <div className="metric-strip">
      {items.map((item) => (
        <div key={item.label} className="metric-strip-item">
          {item.icon ? <span>{item.icon}</span> : null}
          <div>
            <strong>{item.value}</strong>
            <small>{item.label}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

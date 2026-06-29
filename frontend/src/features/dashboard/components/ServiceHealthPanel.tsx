import { Card } from "../../../components/ui/Card";
import { formatStatus } from "../../../utils/formatStatus";
import type { ServiceHealth } from "../types/ServiceHealth";

interface ServiceHealthPanelProps {
  services: ServiceHealth[];
}

export function ServiceHealthPanel({ services }: ServiceHealthPanelProps) {
  return (
    <div className="service-grid">
      {services.map((service) => (
        <Card key={service.label}>
          <h2>{service.label}</h2>
          <p>Status: {formatStatus(service.status)}</p>
          <p>Version: {service.version}</p>
        </Card>
      ))}
    </div>
  );
}

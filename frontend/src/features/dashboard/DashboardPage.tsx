import { PageHeader } from "../../components/common/PageHeader";
import { LoadingState } from "../../components/common/LoadingState";
import { ServiceHealthPanel } from "./components/ServiceHealthPanel";
import { useServiceHealth } from "./hooks/useServiceHealth";

export function DashboardPage() {
  const { data, isError, isLoading } = useServiceHealth();

  if (isLoading) {
    return <LoadingState label="Loading service health" />;
  }

  return (
    <>
      <PageHeader
        title="Platform Dashboard"
        description="Monitor core assessment, code execution, and code evaluation services."
      />
      {isError || !data ? (
        <p>Service health is not available.</p>
      ) : (
        <ServiceHealthPanel services={data} />
      )}
    </>
  );
}

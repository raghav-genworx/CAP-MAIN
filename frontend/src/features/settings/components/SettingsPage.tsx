import { PageHeader } from "../../../components/common/PageHeader";
import { NotificationPreferences } from "../../notifications";

export function SettingsPage() {
  return (
    <section className="ops-page">
      <PageHeader
        title="Settings"
        description="Manage recruiter notification preferences for your workspace."
      />

      <div className="settings-grid">
        <NotificationPreferences />
      </div>
    </section>
  );
}

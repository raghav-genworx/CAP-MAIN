import { Bell, ShieldCheck } from "lucide-react";

import { FormField } from "../../../components/common/FormField";
import { PageHeader } from "../../../components/common/PageHeader";

export function SettingsPage() {
  return (
    <section className="ops-page">
      <PageHeader
        title="Settings"
        description="Workspace defaults for assessment delivery and recruiter notifications."
      />

      <div className="settings-grid">
        <section className="settings-panel">
          <div className="settings-panel-heading">
            <ShieldCheck size={18} aria-hidden="true" />
            <h2>Assessment defaults</h2>
          </div>
          <div className="settings-form-grid">
            <FormField
              label="Default duration"
              inputProps={{ defaultValue: 90, min: 15, step: 5, type: "number" }}
              helperText="Minutes"
            />
            <FormField
              kind="select"
              label="Feedback visibility"
              selectProps={{ defaultValue: "summary" }}
            >
              <option value="summary">Summary after submission</option>
              <option value="none">Hidden from candidates</option>
            </FormField>
          </div>
        </section>

        <section className="settings-panel">
          <div className="settings-panel-heading">
            <Bell size={18} aria-hidden="true" />
            <h2>Notifications</h2>
          </div>
          <label className="toggle-row">
            <input type="checkbox" defaultChecked />
            <span>Notify recruiters when a candidate submits</span>
          </label>
          <label className="toggle-row">
            <input type="checkbox" defaultChecked />
            <span>Send reminder before scheduled tests</span>
          </label>
        </section>
      </div>
    </section>
  );
}

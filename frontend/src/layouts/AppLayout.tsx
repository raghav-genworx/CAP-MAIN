import { Outlet } from "react-router-dom";

import { Sidebar } from "../components/common/Sidebar";
import { Topbar } from "../components/common/Topbar";

export function AppLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Topbar />
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

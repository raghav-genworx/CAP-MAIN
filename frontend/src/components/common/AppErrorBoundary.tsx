import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCcw, TriangleAlert } from "lucide-react";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    globalThis.console.error("CAP frontend render failure", error, info.componentStack);
  }

  private retry = () => {
    this.setState({ hasError: false });
  };

  private reload = () => {
    globalThis.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <main className="app-error-page" role="alert">
        <div className="app-error-panel">
          <span className="app-error-icon" aria-hidden="true">
            <TriangleAlert size={26} />
          </span>
          <div>
            <span className="panel-eyebrow">Workspace interrupted</span>
            <h1>Something went wrong</h1>
            <p>
              Your saved platform data is unaffected. Retry this view or reload the
              application to restore the workspace.
            </p>
          </div>
          <div className="app-error-actions">
            <button type="button" className="button button-secondary" onClick={this.retry}>
              Try again
            </button>
            <button type="button" className="button button-primary" onClick={this.reload}>
              <RefreshCcw size={16} aria-hidden="true" />
              Reload application
            </button>
          </div>
        </div>
      </main>
    );
  }
}

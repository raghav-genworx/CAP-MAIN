import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

describe("AppErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a recoverable fallback when a route render fails", () => {
    let shouldFail = true;
    function RecoverableView() {
      if (shouldFail) {
        throw new Error("render failed");
      }
      return <p>Workspace restored</p>;
    }

    render(
      <AppErrorBoundary>
        <RecoverableView />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");

    shouldFail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.getByText("Workspace restored")).toBeInTheDocument();
  });
});

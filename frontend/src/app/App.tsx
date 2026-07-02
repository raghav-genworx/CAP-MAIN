import { Suspense, useEffect } from "react";
import { RouterProvider } from "react-router-dom";

import { router } from "./routes";
import { LoadingState } from "../components/common/LoadingState";

export function App() {
  useEffect(() => {
    function selectNumericInputValue(event: Event) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "number") {
        return;
      }
      window.requestAnimationFrame(() => target.select());
    }

    function keepNumericInputSelection(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "number") {
        return;
      }
      event.preventDefault();
    }

    document.addEventListener("focusin", selectNumericInputValue);
    document.addEventListener("mouseup", keepNumericInputSelection);
    return () => {
      document.removeEventListener("focusin", selectNumericInputValue);
      document.removeEventListener("mouseup", keepNumericInputSelection);
    };
  }, []);

  return (
    <Suspense fallback={<LoadingState label="Loading page" />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}

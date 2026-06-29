import { Suspense } from "react";
import { RouterProvider } from "react-router-dom";

import { router } from "./app/routes";
import { LoadingState } from "./components/common/LoadingState";

export function App() {
  return (
    <Suspense fallback={<LoadingState label="Loading page" />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}

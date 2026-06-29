import { combineReducers } from "@reduxjs/toolkit";

import { authReducer } from "../features/auth";
import { dashboardReducer } from "../features/dashboard";

export const rootReducer = combineReducers({
  auth: authReducer,
  dashboard: dashboardReducer,
});

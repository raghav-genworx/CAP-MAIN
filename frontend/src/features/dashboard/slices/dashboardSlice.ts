import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface DashboardState {
  selectedService: string | null;
}

const initialState: DashboardState = {
  selectedService: null,
};

const dashboardSlice = createSlice({
  name: "dashboard",
  initialState,
  reducers: {
    selectService(state, action: PayloadAction<string>) {
      state.selectedService = action.payload;
    },
  },
});

export const { selectService } = dashboardSlice.actions;
export const dashboardReducer = dashboardSlice.reducer;

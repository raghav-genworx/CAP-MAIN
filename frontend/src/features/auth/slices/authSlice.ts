import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

import type { AuthUser } from "../types/AuthUser";

export interface AuthState {
  user: AuthUser | null;
}

const initialState: AuthState = {
  user: null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setUser(state, action: PayloadAction<AuthUser>) {
      state.user = action.payload;
    },
    clearUser(state) {
      state.user = null;
    },
  },
});

export const { clearUser, setUser } = authSlice.actions;
export const authReducer = authSlice.reducer;

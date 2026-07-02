export const APP_NAME = "CAP";

export const NAVIGATION_ITEMS = [
  { icon: "dashboard", label: "Dashboard", path: "/recruiter/dashboard" },
  {
    icon: "questions",
    label: "Question Management",
    path: "/recruiter/question-management",
  },
  { icon: "assessments", label: "Assessments", path: "/recruiter/assessments" },
  { icon: "settings", label: "Settings", path: "/recruiter/settings" },
] as const;

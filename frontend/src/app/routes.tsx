import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { ProtectedRoute } from "../features/auth";

const RecruitersPage = lazy(() =>
  import("../features/recruiters").then((module) => ({
    default: module.RecruitersPage,
  })),
);
const QuestionManagementPage = lazy(() =>
  import("../features/assessments").then((module) => ({
    default: module.QuestionManagementPage,
  })),
);
const QuestionCreationFlowPage = lazy(() =>
  import("../features/assessments").then((module) => ({
    default: module.QuestionCreationFlowPage,
  })),
);
const QuestionGroupCreationFlowPage = lazy(() =>
  import("../features/assessments").then((module) => ({
    default: module.QuestionGroupCreationFlowPage,
  })),
);
const RecruiterAssessmentsPage = lazy(() =>
  import("../features/assessments").then((module) => ({
    default: module.RecruiterAssessmentsPage,
  })),
);
const SettingsPage = lazy(() =>
  import("../features/settings").then((module) => ({
    default: module.SettingsPage,
  })),
);
const LoginPage = lazy(() =>
  import("../features/auth").then((module) => ({
    default: module.RecruiterLoginPage,
  })),
);
const EmailVerificationPage = lazy(() =>
  import("../features/auth").then((module) => ({
    default: module.EmailVerificationPage,
  })),
);
const SignupPage = lazy(() =>
  import("../features/auth").then((module) => ({
    default: module.RecruiterSignupPage,
  })),
);
const SubscriptionPage = lazy(() =>
  import("../features/auth").then((module) => ({
    default: module.RecruiterSubscriptionPage,
  })),
);
const CandidateInvitePage = lazy(() =>
  import("../features/candidatePortal").then((module) => ({
    default: module.CandidateInvitePage,
  })),
);
const CandidateCodeEntryPage = lazy(() =>
  import("../features/candidatePortal").then((module) => ({
    default: module.CandidateCodeEntryPage,
  })),
);
const CandidateAssessmentPage = lazy(() =>
  import("../features/candidatePortal").then((module) => ({
    default: module.CandidateAssessmentPage,
  })),
);
const CandidateSubmissionPage = lazy(() =>
  import("../features/candidatePortal").then((module) => ({
    default: module.CandidateSubmissionPage,
  })),
);

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/recruiter/dashboard" replace /> },
  {
    path: "/recruiter/login",
    element: <LoginPage />,
  },
  {
    path: "/recruiter/verify-email",
    element: <EmailVerificationPage />,
  },
  {
    path: "/recruiter/signup",
    element: <SignupPage />,
  },
  {
    element: <ProtectedRoute requireSubscription={false} />,
    children: [
      {
        path: "/recruiter/subscription",
        element: <SubscriptionPage />,
      },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/recruiter/dashboard", element: <RecruitersPage /> },
          {
            path: "/recruiter/question-management",
            element: <QuestionManagementPage />,
          },
          {
            path: "/recruiter/question-management/new",
            element: <QuestionCreationFlowPage />,
          },
          {
            path: "/recruiter/question-management/groups/new",
            element: <QuestionGroupCreationFlowPage />,
          },
          {
            path: "/recruiter/assessments",
            element: <RecruiterAssessmentsPage />,
          },
          {
            path: "/recruiter/candidates",
            element: <Navigate to="/recruiter/assessments" replace />,
          },
          {
            path: "/recruiter/settings",
            element: <SettingsPage />,
          },
          {
            path: "/question-management",
            element: (
              <Navigate to="/recruiter/question-management" replace />
            ),
          },
        ],
      },
    ],
  },
  {
    path: "/candidate",
    element: <CandidateCodeEntryPage />,
  },
  {
    path: "/candidate/join",
    element: <CandidateCodeEntryPage />,
  },
  {
    path: "/candidate/invite/:token",
    element: <CandidateInvitePage />,
  },
  {
    path: "/candidate/portal",
    element: <CandidateAssessmentPage />,
  },
  {
    path: "/candidate/submitted",
    element: <CandidateSubmissionPage />,
  },
  { path: "*", element: <Navigate to="/recruiter/login" replace /> },
]);

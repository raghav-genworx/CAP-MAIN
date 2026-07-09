# CAP Frontend

React 19+ frontend scaffold following the GenWorx COE feature-based architecture.

## Architecture

- `src/app`: application providers and lazy-loaded routes.
- `src/features`: domain modules with feature-specific UI, hooks, services, types, and utilities.
- `src/components`: shared generic UI only, with no business logic.
- `src/lib`: configured third-party clients such as Axios.
- `src/config`: typed environment and static app constants.

## Commands

```bash
npm install
npm run dev
npm run build
npm run lint
```

## Environment

Copy `.env.example` to `.env` and fill the Firebase values before using recruiter login, signup, Google sign-in, or Microsoft sign-in.
# CAP-Frontend

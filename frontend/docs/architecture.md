# Frontend Architecture

This frontend follows the React COE guide's Redux Toolkit structure for medium-to-enterprise applications.

## Target Structure

```text
src/
├── app/                  # App shell, store, reducers, middleware, providers, routes
├── assets/               # Images, fonts, icons
├── components/           # Shared UI with no domain/business logic
│   ├── ui/               # Atomic components
│   ├── common/           # Shared composites and feedback states
│   └── forms/            # Reusable form controls
├── config/               # Type-safe environment and app constants
├── features/             # Domain modules
│   └── <feature>/
│       ├── components/   # Feature-specific UI
│       ├── hooks/        # Feature orchestration and data hooks
│       ├── services/     # Feature API calls
│       ├── slices/       # Redux Toolkit slices when needed
│       ├── types/        # Feature-owned TypeScript models
│       ├── utils/        # Feature-only pure helpers
│       ├── styles/       # Feature-owned styles when global CSS is unavoidable
│       └── index.ts      # Public feature API
├── hooks/                # Global shared hooks
├── layouts/              # Route/page layout shells
├── lib/                  # Third-party library clients and adapters
├── styles/               # Global styles
├── test/                 # Global test setup and mocks
├── types/                # Global TypeScript contracts
└── utils/                # Pure shared helpers
```

## Folder Rules

- Put domain code inside `src/features/<feature>`.
- Keep feature roots limited to `index.ts`; implementation belongs in the feature subfolders.
- Keep shared UI in `src/components` only when it has no business logic.
- Put API client configuration in `src/lib`.
- Put endpoint-specific service calls inside feature `services` folders. Keep `src/services` unused unless a genuinely app-wide service appears.
- Export only public feature APIs from each feature `index.ts`.
- Use React Query for server state and Redux for cross-feature client state.
- Lazy-load route-level feature pages from `src/app/routes.tsx`.
- Keep direct API clients out of components and hooks; components call hooks, hooks call services.
- Keep app-wide shell code under `src/app`; `src/main.tsx` should stay a thin entry point.

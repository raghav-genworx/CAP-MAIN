# Frontend Architecture

This frontend follows the React COE guide's feature-based structure for medium-to-enterprise applications. React Query owns server state, while React context and local component state own the small amount of shared client state.

## Target Structure

```text
src/
├── app/                  # App shell, providers, and lazy-loaded routes
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
│       ├── state/        # Optional feature state when local/context state is insufficient
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
- Use React Query for server state. Prefer local state or a narrowly scoped context for client state; add a state library only when the application has demonstrated cross-feature state needs.
- Lazy-load route-level feature pages from `src/app/routes.tsx`.
- Keep direct API clients out of components and hooks; components call hooks, hooks call services.
- Keep app-wide shell code under `src/app`; `src/main.tsx` should stay a thin entry point.

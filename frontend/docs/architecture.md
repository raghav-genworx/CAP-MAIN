# Frontend Architecture

This frontend follows the React COE guide's Redux Toolkit structure for medium-to-enterprise applications.

## Folder Rules

- Put domain code inside `src/features/<feature>`.
- Keep shared UI in `src/components` only when it has no business logic.
- Put API client configuration in `src/lib`.
- Put endpoint-specific service calls inside feature `services` folders.
- Export only public feature APIs from each feature `index.ts`.
- Use React Query for server state and Redux for cross-feature client state.

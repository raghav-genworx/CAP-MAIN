"""ASGI applications served from this codebase.

The consolidation keeps four deployables while the code lives in one tree: `core`,
`execution`, `evaluation` and `gateway`. Each module here assembles only the routers
belonging to its bounded contexts, which is what keeps a context extractable -- an
application factory is the seam a future split would cut along.

Phase 5 folds `gateway` into `core`; the remaining factories stay as the extraction
seam.
"""

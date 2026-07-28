"""Application entry point.

One image serves four deployables. ``CAP_APP`` selects which application this
process runs and defaults to ``core``, so the existing ``uvicorn main:app`` command
keeps starting the core platform unchanged.

Only the selected application is constructed: importing all four eagerly would make
every container pay for the others' dependencies -- and would build the gateway's
catch-all proxy route inside the core process, where it must never exist.
"""

import os

from fastapi import FastAPI

APP_NAMES = ("core", "execution", "evaluation", "gateway")


def create_app(name: str | None = None) -> FastAPI:
    """Create the application named by ``name`` or ``CAP_APP``."""

    selected = (name or os.getenv("CAP_APP") or "core").strip().lower()
    if selected not in APP_NAMES:
        raise RuntimeError(
            f"Unknown CAP_APP {selected!r}; expected one of {', '.join(APP_NAMES)}"
        )

    if selected == "execution":
        from api.rest.apps.execution import create_app as factory
    elif selected == "evaluation":
        from api.rest.apps.evaluation import create_app as factory
    elif selected == "gateway":
        from api.rest.apps.gateway import create_app as factory
    else:
        from api.rest.apps.core import create_app as factory

    return factory()


app = create_app()

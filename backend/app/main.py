from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_company,
    admin_super,
    auth,
    corrections,
    dashboard,
    documents,
    events,
    ingest,
)
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DocuEngine API",
        version="0.1.0",
        docs_url="/docs" if settings.docuengine_env != "production" else None,
    )

    if settings.docuengine_env == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(admin_super.router, prefix=prefix)
    app.include_router(admin_company.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(corrections.router, prefix=prefix)
    app.include_router(ingest.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)

    @app.get(f"{prefix}/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

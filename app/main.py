from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import load_settings
from app.routes import Services, router
from app.services.palette_service import PaletteService
from app.services.pantone_provider import CsvPantoneProvider, SqliteTcxProvider
from app.services.photo_service import PhotoTcxService
from app.services.storage import PaletteStorage


BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    settings = load_settings(BASE_DIR)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=None if settings.hide_docs else "/docs",
        redoc_url=None if settings.hide_docs else "/redoc",
        openapi_url=None if settings.hide_docs else "/openapi.json",
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    settings.palette_db_path.parent.mkdir(parents=True, exist_ok=True)

    if settings.tcx_db_path.exists():
        pantone_provider = SqliteTcxProvider(settings.tcx_db_path)
    else:
        pantone_provider = CsvPantoneProvider(settings.pantone_csv_path)
    palette_service = PaletteService(pantone_provider=pantone_provider)
    photo_service = PhotoTcxService(provider=pantone_provider)
    storage = PaletteStorage(settings.palette_db_path)

    app.state.services = Services(
        palette_service=palette_service,
        storage=storage,
        photo_service=photo_service,
    )
    app.state.settings = settings

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
    app.include_router(router)
    return app


app = create_app()

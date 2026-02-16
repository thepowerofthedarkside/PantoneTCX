from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import Services, router
from app.services.palette_service import PaletteService
from app.services.pantone_provider import CsvPantoneProvider, SqliteTcxProvider
from app.services.photo_service import PhotoTcxService
from app.services.storage import PaletteStorage


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "palette_service.sqlite3"
TCX_DB_PATH = BASE_DIR / "paleton_tcx.sqlite3"


def create_app() -> FastAPI:
    app = FastAPI(title="Palette Generator", version="0.1.0")

    if TCX_DB_PATH.exists():
        pantone_provider = SqliteTcxProvider(TCX_DB_PATH)
    else:
        pantone_provider = CsvPantoneProvider(DATA_DIR / "pantone_stub.csv")
    palette_service = PaletteService(pantone_provider=pantone_provider)
    photo_service = PhotoTcxService(provider=pantone_provider)
    storage = PaletteStorage(DB_PATH)

    app.state.services = Services(palette_service=palette_service, storage=storage, photo_service=photo_service)

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
    app.include_router(router)
    return app


app = create_app()

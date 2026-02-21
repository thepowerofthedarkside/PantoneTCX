from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    app_env: str
    hide_docs: bool
    palette_db_path: Path
    tcx_db_path: Path
    pantone_csv_path: Path
    trusted_hosts: list[str]
    cors_allow_origins: list[str]
    yookassa_shop_id: str | None
    yookassa_secret_key: str | None
    yookassa_return_url: str | None


def load_settings(base_dir: Path) -> Settings:
    data_dir = base_dir / "data"
    app_env = os.getenv("APP_ENV", "development").strip().lower()

    hide_docs = os.getenv("HIDE_DOCS", "").strip().lower() in {"1", "true", "yes"}
    if app_env == "production":
        hide_docs = True if os.getenv("HIDE_DOCS", "").strip() == "" else hide_docs

    trusted_hosts = _csv_env("TRUSTED_HOSTS") or ["*"]
    if "*" not in trusted_hosts:
        for host in ("127.0.0.1", "localhost", "testserver"):
            if host not in trusted_hosts:
                trusted_hosts.append(host)

    return Settings(
        app_name=os.getenv("APP_NAME", "Palette Generator"),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        app_env=app_env,
        hide_docs=hide_docs,
        palette_db_path=Path(os.getenv("PALETTE_DB_PATH", str(base_dir / "palette_service.sqlite3"))),
        tcx_db_path=Path(os.getenv("TCX_DB_PATH", str(base_dir / "paleton_tcx.sqlite3"))),
        pantone_csv_path=Path(os.getenv("PANTONE_CSV_PATH", str(data_dir / "pantone_stub.csv"))),
        trusted_hosts=trusted_hosts,
        cors_allow_origins=_csv_env("CORS_ALLOW_ORIGINS"),
        yookassa_shop_id=(os.getenv("YOOKASSA_SHOP_ID", "").strip() or None),
        yookassa_secret_key=(os.getenv("YOOKASSA_SECRET_KEY", "").strip() or None),
        yookassa_return_url=(os.getenv("YOOKASSA_RETURN_URL", "").strip() or None),
    )

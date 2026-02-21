from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.routes import Services
from app.services.storage import PaletteStorage


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    storage = PaletteStorage(tmp_path / "test.sqlite3")
    app.state.services = Services(app.state.services.palette_service, storage, app.state.services.photo_service)
    return TestClient(app)


def _sample_image_bytes() -> bytes:
    img = Image.new("RGB", (120, 80), (210, 108, 49))
    for x in range(60, 120):
        for y in range(0, 80):
            img.putpixel((x, y), (40, 130, 170))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_health(tmp_path: Path):
    client = _client(tmp_path)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_has_seo_tags(tmp_path: Path):
    client = _client(tmp_path)
    res = client.get("/")
    assert res.status_code == 200
    assert "<meta name=\"description\"" in res.text
    assert "<link rel=\"canonical\"" in res.text
    assert "application/ld+json" in res.text


def test_robots_and_sitemap(tmp_path: Path):
    client = _client(tmp_path)
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "Sitemap:" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "<urlset" in sitemap.text
    assert "<loc>" in sitemap.text


def test_generate_and_get_by_id(tmp_path: Path):
    client = _client(tmp_path)
    payload = {
        "season": "SS",
        "audience": "mass",
        "style": "street",
        "geography": "EU",
        "key_color": "#D26C31",
        "count": 6,
    }
    res = client.post("/api/palette/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["palette"]) == 6
    palette_id = data["id"]

    get_res = client.get(f"/api/palette/{palette_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == palette_id


def test_generate_with_tcx_code_key_color(tmp_path: Path):
    client = _client(tmp_path)
    payload = {
        "season": "SS",
        "audience": "mass",
        "style": "street",
        "geography": "EU",
        "key_color_mode": "tcx_code",
        "key_color_value": "17-0836",
        "count": 6,
    }
    res = client.post("/api/palette/generate", json=payload)
    assert res.status_code == 200
    assert len(res.json()["palette"][0]["pantone_matches"]) > 0


def test_generate_with_base_role_key_color(tmp_path: Path):
    client = _client(tmp_path)
    payload = {
        "season": "SS",
        "audience": "mass",
        "style": "street",
        "geography": "EU",
        "key_color_mode": "tcx_code",
        "key_color_value": "17-0836",
        "key_color_role": "base",
        "count": 6,
    }
    res = client.post("/api/palette/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    base_items = [x for x in data["palette"] if x["role"] == "base"]
    assert any(x["hex"] == "#927B3C" for x in base_items)


def test_pdf_endpoint_returns_pdf(tmp_path: Path):
    client = _client(tmp_path)
    payload = {
        "season": "FW",
        "audience": "premium",
        "style": "classic",
        "geography": "RU",
        "key_color": "#4A5C8A",
        "count": 6,
    }
    res = client.post("/api/palette/generate", json=payload)
    palette_id = res.json()["id"]

    pdf_res = client.get(f"/api/palette/{palette_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"].startswith("application/pdf")
    assert len(pdf_res.content) > 500


def test_ui_index_and_generate(tmp_path: Path):
    client = _client(tmp_path)
    idx = client.get("/")
    assert idx.status_code == 200

    form = {
        "season": "SS",
        "audience": "mass",
        "style": "street",
        "key_color_mode": "tcx_name",
        "key_color_value": "Ecru Olive",
        "count": "6",
    }
    out = client.post("/generate", data=form)
    assert out.status_code == 200
    assert "Палитра коллекции" in out.text
    assert 'class="swatch-link"' in out.text


def test_ui_donate_success_page(tmp_path: Path):
    client = _client(tmp_path)
    res = client.get("/donate/success")
    assert res.status_code == 200
    assert "Спасибо за поддержку" in res.text


def test_ui_generate_without_key_color(tmp_path: Path):
    client = _client(tmp_path)
    form = {
        "season": "SS",
        "audience": "mass",
        "style": "street",
        "key_color_mode": "hex",
        "key_color_value": "",
        "count": "6",
    }
    out = client.post("/generate", data=form)
    assert out.status_code == 200
    assert "Палитра коллекции" in out.text


def test_api_photo_tcx(tmp_path: Path):
    client = _client(tmp_path)
    files = {"image": ("sample.png", _sample_image_bytes(), "image/png")}
    data = {"count": "4"}
    res = client.post("/api/photo/tcx", files=files, data=data)
    assert res.status_code == 200
    payload = res.json()
    assert payload["count"] >= 1
    assert len(payload["colors"]) >= 1
    assert "tcx_matches" in payload["colors"][0]


def test_ui_photo_analyze(tmp_path: Path):
    client = _client(tmp_path)
    files = {"image": ("sample.png", _sample_image_bytes(), "image/png")}
    data = {"count": "4"}
    res = client.post("/photo/analyze", files=files, data=data)
    assert res.status_code == 200
    assert "Результат анализа фото" in res.text
    assert 'class="swatch-link"' in res.text


def test_api_tcx_match_color(tmp_path: Path):
    client = _client(tmp_path)
    res = client.post("/api/tcx/match-color", json={"hex": "#927B3C", "k": 3})
    assert res.status_code == 200
    data = res.json()
    assert data["hex"] == "#927B3C"
    assert len(data["tcx_matches"]) >= 1


def test_api_tcx_detail_by_code(tmp_path: Path):
    client = _client(tmp_path)
    res = client.get("/api/tcx/17-0836")
    assert res.status_code == 200
    data = res.json()
    assert data["code"] == "17-0836"
    assert data["name"].lower() == "ecru olive"


def test_api_color_convert_from_hex(tmp_path: Path):
    client = _client(tmp_path)
    res = client.post("/api/color/convert", json={"input_mode": "auto", "value": "#927B3C"})
    assert res.status_code == 200
    data = res.json()
    assert data["hex"] == "#927B3C"
    assert data["resolved_mode"] == "hex"
    assert len(data["rgb"]) == 3
    assert len(data["cmyk"]) == 4
    assert len(data["lab"]) == 3
    assert data["tcx_match"] is not None


def test_api_color_convert_from_tcx_code(tmp_path: Path):
    client = _client(tmp_path)
    res = client.post("/api/color/convert", json={"input_mode": "auto", "value": "17-0836"})
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_mode"] == "tcx_code"
    assert data["hex"] == "#927B3C"


def test_api_donate_endpoints_not_configured(tmp_path: Path):
    client = _client(tmp_path)
    settings = client.app.state.settings
    client.app.state.settings = type(settings)(
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        hide_docs=settings.hide_docs,
        palette_db_path=settings.palette_db_path,
        tcx_db_path=settings.tcx_db_path,
        pantone_csv_path=settings.pantone_csv_path,
        trusted_hosts=settings.trusted_hosts,
        cors_allow_origins=settings.cors_allow_origins,
        yookassa_shop_id=None,
        yookassa_secret_key=None,
        yookassa_return_url=settings.yookassa_return_url,
    )

    create_res = client.post("/api/donate/create-payment", json={"amount": "300.00"})
    assert create_res.status_code == 503
    assert "YooKassa is not configured" in create_res.json()["detail"]

    status_res = client.get("/api/donate/payment-status/test-payment-id")
    assert status_res.status_code == 503
    assert "YooKassa is not configured" in status_res.json()["detail"]


def test_ui_tcx_detail_page(tmp_path: Path):
    client = _client(tmp_path)
    res = client.get("/tcx/17-0836")
    assert res.status_code == 200
    assert "17-0836" in res.text
    assert "Ecru Olive" in res.text
    assert "Оттенки" in res.text
    assert "Цветовые гармонии" in res.text
    assert "Палитра коллекции" in res.text
    assert "Источник:" not in res.text

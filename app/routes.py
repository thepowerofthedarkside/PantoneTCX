from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.schemas import (
    ConvertColorRequest,
    ConvertColorResponse,
    DonateCreatePaymentRequest,
    DonateCreatePaymentResponse,
    GeneratePaletteRequest,
    HealthResponse,
    MatchColorRequest,
    MatchColorResponse,
    PaletteResponse,
)
from app.services.color_math import (
    cmyk_to_rgb,
    hex_to_lab,
    hex_to_rgb,
    lab_to_hex,
    lab_to_lch,
    lch_to_lab,
    rgb_to_cmyk,
    rgb_to_hex,
    rgb_to_lab,
)
from app.services.palette_service import PaletteService
from app.services.pdf_export import build_palette_pdf
from app.services.photo_service import PhotoTcxService
from app.services.storage import PaletteStorage


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


class Services:
    def __init__(self, palette_service: PaletteService, storage: PaletteStorage, photo_service: PhotoTcxService) -> None:
        self.palette_service = palette_service
        self.storage = storage
        self.photo_service = photo_service


def get_services(request: Request) -> Services:
    return request.app.state.services


def _to_palette_response(record: dict) -> dict:
    created_at = datetime.fromisoformat(record["created_at"])
    return {
        "id": record["id"],
        "input": record["input"],
        "palette": record["result"]["palette"],
        "checks": record["result"]["checks"],
        "created_at": created_at,
    }


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _index_seo_context(request: Request) -> dict:
    base_url = _base_url(request)
    canonical = f"{base_url}/"
    structured_data = [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Генератор палитры коллекции",
            "url": canonical,
            "inLanguage": "ru-RU",
        },
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": "Генератор палитры коллекции",
            "applicationCategory": "DesignApplication",
            "operatingSystem": "Any",
            "url": canonical,
            "description": (
                "Онлайн сервис для генерации палитр, конвертации HEX/RGB/CMYK/LAB "
                "и подбора ближайших цветов Pantone TCX."
            ),
            "inLanguage": "ru-RU",
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "Как сгенерировать палитру коллекции?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Выберите параметры сезона, аудитории и стиля, затем нажмите «Сгенерировать».",
                    },
                },
                {
                    "@type": "Question",
                    "name": "Можно ли конвертировать цвет из одного формата в другой?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Да. В блоке «Конвертация цвета» вставьте одно значение, и сервис вернет HEX, RGB, CMYK и LAB.",
                    },
                },
                {
                    "@type": "Question",
                    "name": "Как подобрать ближайший Pantone TCX?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Сервис автоматически рассчитывает ближайший TCX цвет по DeltaE00 и показывает карточку цвета.",
                    },
                },
            ],
        },
    ]
    return {
        "title": "Генератор палитры и конвертер цветов HEX RGB CMYK LAB | Pantone TCX",
        "description": (
            "Генератор палитры коллекции и онлайн конвертер цветов. "
            "Подбор ближайших Pantone TCX, анализ фото и экспорт палитры в PDF."
        ),
        "keywords": (
            "генератор палитры, конвертер цвета, hex rgb cmyk lab, "
            "pantone tcx, подбор цвета, цветовая палитра коллекции"
        ),
        "canonical": canonical,
        "structured_data": [json.dumps(item, ensure_ascii=False) for item in structured_data],
    }


def _parse_number_list(value: str, expected_len: int) -> list[float]:
    cleaned = value.strip().lower().replace("rgb(", "").replace("cmyk(", "").replace("lab(", "")
    cleaned = cleaned.replace(")", "").replace(";", ",")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if len(parts) != expected_len:
        raise ValueError(f"Expected {expected_len} values, got {len(parts)}")
    try:
        return [float(x) for x in parts]
    except ValueError as exc:
        raise ValueError("Color components must be numeric") from exc


def _detect_input_mode(value: str) -> str:
    v = value.strip()
    if v.startswith("#") and len(v) == 7:
        return "hex"

    low = v.lower()
    if low.count(",") == 2:
        return "lab" if "lab" in low else "rgb"
    if low.count(",") == 3:
        return "cmyk"
    if "-" in v and any(ch.isdigit() for ch in v):
        return "tcx_code"
    return "tcx_name"


def _resolve_input_to_rgb_lab(
    services: Services,
    mode: str,
    value: str,
) -> tuple[tuple[int, int, int], tuple[float, float, float], str]:
    provider = services.palette_service.pantone_provider
    normalized_mode = mode.lower()
    normalized_value = value.strip()

    if normalized_mode == "hex":
        rgb = hex_to_rgb(normalized_value.upper())
        return rgb, rgb_to_lab(rgb), "hex"

    if normalized_mode == "rgb":
        comps = _parse_number_list(normalized_value, expected_len=3)
        rgb = (
            max(0, min(255, round(comps[0]))),
            max(0, min(255, round(comps[1]))),
            max(0, min(255, round(comps[2]))),
        )
        return rgb, rgb_to_lab(rgb), "rgb"

    if normalized_mode == "cmyk":
        comps = _parse_number_list(normalized_value, expected_len=4)
        rgb = cmyk_to_rgb((comps[0], comps[1], comps[2], comps[3]))
        return rgb, rgb_to_lab(rgb), "cmyk"

    if normalized_mode == "lab":
        comps = _parse_number_list(normalized_value, expected_len=3)
        lab = (
            max(0.0, min(100.0, comps[0])),
            max(-128.0, min(128.0, comps[1])),
            max(-128.0, min(128.0, comps[2])),
        )
        return hex_to_rgb(lab_to_hex(lab)), lab, "lab"

    if normalized_mode == "tcx_code":
        entry = provider.get_by_code(normalized_value)
        if not entry:
            raise ValueError("TCX color not found by code")
        if entry.hex:
            rgb = hex_to_rgb(entry.hex)
            return rgb, rgb_to_lab(rgb), "tcx_code"
        rgb = hex_to_rgb(lab_to_hex(entry.lab))
        return rgb, entry.lab, "tcx_code"

    if normalized_mode == "tcx_name":
        entry = provider.get_by_name(normalized_value)
        if not entry:
            raise ValueError("TCX color not found by name")
        if entry.hex:
            rgb = hex_to_rgb(entry.hex)
            return rgb, rgb_to_lab(rgb), "tcx_name"
        rgb = hex_to_rgb(lab_to_hex(entry.lab))
        return rgb, entry.lab, "tcx_name"

    raise ValueError(f"Unsupported input mode: {mode}")


def _build_tcx_detail(services: Services, entry_code: str) -> dict:
    provider = services.palette_service.pantone_provider
    entry = provider.get_by_code(entry_code)
    if not entry:
        raise HTTPException(status_code=404, detail="TCX color not found")

    hex_color = entry.hex or lab_to_hex(entry.lab)
    rgb = hex_to_rgb(hex_color)
    cmyk = rgb_to_cmyk(rgb)
    matches = []
    for m in provider.match_top_k(entry.lab, k=8):
        if m.code.lower() == entry.code.lower():
            continue
        similar_entry = provider.get_by_code(m.code)
        matches.append(
            {
                "code": m.code,
                "name": m.name,
                "hex": similar_entry.hex if similar_entry else None,
                "rgb": hex_to_rgb(similar_entry.hex) if similar_entry and similar_entry.hex else None,
                "cmyk": rgb_to_cmyk(hex_to_rgb(similar_entry.hex)) if similar_entry and similar_entry.hex else None,
                "lab": (
                    (round(similar_entry.lab[0], 2), round(similar_entry.lab[1], 2), round(similar_entry.lab[2], 2))
                    if similar_entry
                    else None
                ),
            }
        )
        if len(matches) >= 5:
            break

    shades: list[dict] = []
    l0, c0, h0 = lab_to_lch(entry.lab)
    shade_levels = [85, 75, 65, 55, 45, 35, 25]
    for level in shade_levels:
        lab = lch_to_lab((float(level), c0, h0))
        shade_hex = lab_to_hex(lab)
        nearest = provider.match_top_k(lab, k=1)
        nearest_item = (
            {"code": nearest[0].code, "name": nearest[0].name, "delta_e00": round(nearest[0].delta_e00, 2)}
            if nearest
            else None
        )
        shades.append(
            {
                "label": f"Оттенок {len(shades) + 1}",
                "hex": shade_hex,
                "rgb": hex_to_rgb(shade_hex),
                "cmyk": rgb_to_cmyk(hex_to_rgb(shade_hex)),
                "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
                "nearest_tcx": nearest_item,
            }
        )

    def make_harmony_color(label: str, l_val: float, c_val: float, h_val: float) -> dict:
        lab = lch_to_lab((float(l_val), float(c_val), float(h_val % 360)))
        hex_val = lab_to_hex(lab)
        nearest = provider.match_top_k(lab, k=1)
        nearest_item = (
            {"code": nearest[0].code, "name": nearest[0].name, "delta_e00": round(nearest[0].delta_e00, 2)}
            if nearest
            else None
        )
        return {
            "label": label,
            "hex": hex_val,
            "rgb": hex_to_rgb(hex_val),
            "cmyk": rgb_to_cmyk(hex_to_rgb(hex_val)),
            "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
            "nearest_tcx": nearest_item,
        }

    harmonies = [
        {
            "name": "Комплементарная",
            "items": [make_harmony_color("Комплементарный", l0, c0, h0 + 180)],
        },
        {
            "name": "Аналоговая",
            "items": [
                make_harmony_color("Соседний А", l0, c0, h0 - 30),
                make_harmony_color("Соседний Б", l0, c0, h0 + 30),
            ],
        },
        {
            "name": "Триада",
            "items": [
                make_harmony_color("Триада А", l0, c0, h0 + 120),
                make_harmony_color("Триада Б", l0, c0, h0 + 240),
            ],
        },
        {
            "name": "Разделенная комплементарная",
            "items": [
                make_harmony_color("Разделение А", l0, c0, h0 + 150),
                make_harmony_color("Разделение Б", l0, c0, h0 + 210),
            ],
        },
        {
            "name": "Тоны (снижение насыщенности)",
            "items": [
                make_harmony_color("Тон 80%", l0, c0 * 0.8, h0),
                make_harmony_color("Тон 60%", l0, c0 * 0.6, h0),
                make_harmony_color("Тон 40%", l0, c0 * 0.4, h0),
            ],
        },
    ]

    seed = int(hashlib.sha1(entry.code.encode("utf-8")).hexdigest()[:8], 16)
    preview_request = GeneratePaletteRequest(
        season="none",
        audience="none",
        style="none",
        geography="N/A",
        key_color_mode="tcx_code",
        key_color_value=entry.code,
        key_color_role="base",
        count=6,
        seed=seed,
    )
    preview = services.palette_service.generate(preview_request)

    return {
        "code": entry.code,
        "name": entry.name,
        "hex": hex_color,
        "rgb": rgb,
        "cmyk": cmyk,
        "lab": (round(entry.lab[0], 2), round(entry.lab[1], 2), round(entry.lab[2], 2)),
        "similar": matches,
        "shades": shades,
        "harmonies": harmonies,
        "collection_preview": preview["palette"],
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request) -> PlainTextResponse:
    base_url = _base_url(request)
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /health\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return PlainTextResponse(content)


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request, services: Services = Depends(get_services)) -> Response:
    base_url = _base_url(request)
    urls = [f"{base_url}/"]
    for entry in services.palette_service.pantone_provider.list_entries()[:150]:
        urls.append(f"{base_url}/tcx/{entry.code}")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url)}</loc>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines), media_type="application/xml")


@router.post("/api/donate/create-payment", response_model=DonateCreatePaymentResponse)
async def api_donate_create_payment(payload: DonateCreatePaymentRequest, request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise HTTPException(status_code=503, detail="YooKassa is not configured on server")

    base_url = _base_url(request)
    return_url = settings.yookassa_return_url or f"{base_url}/"
    amount_value = f"{payload.amount:.2f}"
    payment_request = {
        "amount": {"value": amount_value, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "embedded"},
        "description": "Пожертвование на развитие проекта Pantone TCX",
        "metadata": {"source": "website_donation"},
    }
    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.yookassa.ru/v3/payments",
                json=payment_request,
                auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to reach YooKassa API") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"YooKassa API error: {resp.status_code}")

    data = resp.json()
    confirmation = data.get("confirmation") or {}
    token = confirmation.get("confirmation_token")
    payment_id = data.get("id")
    if not token or not payment_id:
        raise HTTPException(status_code=502, detail="YooKassa did not return confirmation token")

    return {
        "payment_id": payment_id,
        "confirmation_token": token,
        "amount": round(payload.amount, 2),
        "currency": "RUB",
        "return_url": return_url,
    }


@router.post("/api/tcx/match-color", response_model=MatchColorResponse)
def api_tcx_match_color(
    payload: MatchColorRequest,
    services: Services = Depends(get_services),
) -> dict:
    lab = hex_to_lab(payload.hex)
    rgb = hex_to_rgb(payload.hex)
    matches = services.palette_service.pantone_provider.match_top_k(lab, k=payload.k)
    provider = services.palette_service.pantone_provider
    return {
        "hex": payload.hex,
        "rgb": rgb,
        "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
        "tcx_matches": [
            (
                lambda entry: {
                    "code": m.code,
                    "name": m.name,
                    "hex": entry.hex if entry else None,
                    "rgb": hex_to_rgb(entry.hex) if entry and entry.hex else None,
                    "cmyk": rgb_to_cmyk(hex_to_rgb(entry.hex)) if entry and entry.hex else None,
                    "lab": (
                        (round(entry.lab[0], 2), round(entry.lab[1], 2), round(entry.lab[2], 2)) if entry else None
                    ),
                    "delta_e00": round(m.delta_e00, 2),
                }
            )(provider.get_by_code(m.code))
            for m in matches
        ],
    }


@router.post("/api/color/convert", response_model=ConvertColorResponse)
def api_color_convert(payload: ConvertColorRequest, services: Services = Depends(get_services)) -> dict:
    mode = payload.input_mode.lower()
    if mode == "auto":
        mode = _detect_input_mode(payload.value)

    try:
        rgb, lab, resolved_mode = _resolve_input_to_rgb_lab(services, mode, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    hex_value = rgb_to_hex(rgb)
    cmyk = rgb_to_cmyk(rgb)

    top_match = services.palette_service.pantone_provider.match_top_k(lab, k=1)
    tcx_match = None
    if top_match:
        match = top_match[0]
        entry = services.palette_service.pantone_provider.get_by_code(match.code)
        tcx_match = {
            "code": match.code,
            "name": match.name,
            "hex": entry.hex if entry else None,
            "rgb": hex_to_rgb(entry.hex) if entry and entry.hex else None,
            "cmyk": rgb_to_cmyk(hex_to_rgb(entry.hex)) if entry and entry.hex else None,
            "lab": (round(entry.lab[0], 2), round(entry.lab[1], 2), round(entry.lab[2], 2)) if entry else None,
            "delta_e00": round(match.delta_e00, 2),
        }

    return {
        "input_mode": payload.input_mode,
        "resolved_mode": resolved_mode,
        "value": payload.value,
        "hex": hex_value,
        "rgb": rgb,
        "cmyk": cmyk,
        "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
        "tcx_match": tcx_match,
    }


@router.get("/api/tcx/{tcx_code}")
def api_tcx_by_code(tcx_code: str, services: Services = Depends(get_services)) -> dict:
    return _build_tcx_detail(services, tcx_code)


@router.get("/tcx/{tcx_code}", response_class=HTMLResponse)
def tcx_detail_page(tcx_code: str, request: Request, services: Services = Depends(get_services)) -> HTMLResponse:
    detail = _build_tcx_detail(services, tcx_code)
    return templates.TemplateResponse(
        request,
        "tcx_detail.html",
        {
            "request": request,
            "color": detail,
        },
    )


@router.post("/api/palette/generate", response_model=PaletteResponse)
def api_generate_palette(
    payload: GeneratePaletteRequest,
    services: Services = Depends(get_services),
) -> dict:
    try:
        result = services.palette_service.generate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    palette_id, created_at = services.storage.save(payload.model_dump(), result)
    return {
        "id": palette_id,
        "input": payload.model_dump(),
        "palette": result["palette"],
        "checks": result["checks"],
        "created_at": created_at,
    }


@router.get("/api/palette/{palette_id}", response_model=PaletteResponse)
def api_get_palette(palette_id: str, services: Services = Depends(get_services)) -> dict:
    row = services.storage.get(palette_id)
    if not row:
        raise HTTPException(status_code=404, detail="Palette not found")
    return _to_palette_response(row)


@router.get("/api/palette/{palette_id}/pdf")
def api_get_palette_pdf(palette_id: str, services: Services = Depends(get_services)) -> Response:
    row = services.storage.get(palette_id)
    if not row:
        raise HTTPException(status_code=404, detail="Palette not found")

    response_data = _to_palette_response(row)
    pdf_bytes = build_palette_pdf(response_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=palette_{palette_id}.pdf"},
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    defaults = {
        "season": "none",
        "audience": "none",
        "style": "none",
        "key_color_mode": "hex",
        "key_color_value": "",
        "key_color_role": "accent",
        "key_color": "",
        "count": 6,
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "defaults": defaults,
            "seo": _index_seo_context(request),
        },
    )


@router.post("/api/photo/tcx")
async def api_photo_tcx(
    image: UploadFile = File(...),
    count: int = Form(6),
    services: Services = Depends(get_services),
) -> dict:
    data = await image.read()
    try:
        return services.photo_service.analyze(data, count=count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/photo/analyze", response_class=HTMLResponse)
async def photo_analyze_form(
    request: Request,
    image: UploadFile = File(...),
    count: int = Form(6),
    services: Services = Depends(get_services),
) -> HTMLResponse:
    data = await image.read()
    try:
        result = services.photo_service.analyze(data, count=count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "photo_result.html",
        {
            "request": request,
            "filename": image.filename or "uploaded-image",
            "count_requested": count,
            "result": result,
        },
    )


@router.post("/generate", response_class=HTMLResponse)
def generate_form(
    request: Request,
    season: str = Form(...),
    audience: str = Form(...),
    style: str = Form(...),
    key_color_mode: str = Form("hex"),
    key_color_value: str = Form(""),
    key_color_role: str = Form("accent"),
    key_color: str = Form(""),
    count: int = Form(6),
    services: Services = Depends(get_services),
) -> HTMLResponse:
    normalized_value = (key_color_value or "").strip() or None
    normalized_legacy = (key_color or "").strip() or None
    normalized_mode = (key_color_mode or "").strip() or None
    if normalized_value is None and normalized_legacy is None:
        normalized_mode = None

    try:
        payload = GeneratePaletteRequest(
            season=season,
            audience=audience,
            style=style,
            geography="N/A",
            key_color_mode=normalized_mode,
            key_color_value=normalized_value,
            key_color_role=key_color_role or "accent",
            key_color=normalized_legacy,
            count=count,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    try:
        result = services.palette_service.generate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    palette_id, created_at = services.storage.save(payload.model_dump(), result)

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "request": request,
            "id": palette_id,
            "created_at": created_at,
            "input": payload.model_dump(),
            "palette": result["palette"],
            "checks": result["checks"],
        },
    )

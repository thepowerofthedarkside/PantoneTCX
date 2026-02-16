from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.schemas import (
    GeneratePaletteRequest,
    HealthResponse,
    MatchColorRequest,
    MatchColorResponse,
    PaletteResponse,
)
from app.services.color_math import hex_to_lab, hex_to_rgb, lab_to_hex, lab_to_lch, lch_to_lab, rgb_to_cmyk
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
                "label": f"Shade {len(shades) + 1}",
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
            "items": [make_harmony_color("Дополняющий", l0, c0, h0 + 180)],
        },
        {
            "name": "Аналоговая",
            "items": [
                make_harmony_color("Соседний A", l0, c0, h0 - 30),
                make_harmony_color("Соседний B", l0, c0, h0 + 30),
            ],
        },
        {
            "name": "Триада",
            "items": [
                make_harmony_color("Триада A", l0, c0, h0 + 120),
                make_harmony_color("Триада B", l0, c0, h0 + 240),
            ],
        },
        {
            "name": "Split-Complementary",
            "items": [
                make_harmony_color("Split A", l0, c0, h0 + 150),
                make_harmony_color("Split B", l0, c0, h0 + 210),
            ],
        },
        {
            "name": "Тоны (снижение chroma)",
            "items": [
                make_harmony_color("Tone 80%", l0, c0 * 0.8, h0),
                make_harmony_color("Tone 60%", l0, c0 * 0.6, h0),
                make_harmony_color("Tone 40%", l0, c0 * 0.4, h0),
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


@router.post("/api/tcx/match-color", response_model=MatchColorResponse)
def api_tcx_match_color(
    payload: MatchColorRequest,
    services: Services = Depends(get_services),
) -> dict:
    lab = hex_to_lab(payload.hex)
    rgb = hex_to_rgb(payload.hex)
    matches = services.palette_service.pantone_provider.match_top_k(lab, k=payload.k)
    return {
        "hex": payload.hex,
        "rgb": rgb,
        "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
        "tcx_matches": [
            {
                "code": m.code,
                "name": m.name,
                "hex": (
                    services.palette_service.pantone_provider.get_by_code(m.code).hex
                    if services.palette_service.pantone_provider.get_by_code(m.code)
                    else None
                ),
                "rgb": (
                    hex_to_rgb(services.palette_service.pantone_provider.get_by_code(m.code).hex)
                    if services.palette_service.pantone_provider.get_by_code(m.code)
                    and services.palette_service.pantone_provider.get_by_code(m.code).hex
                    else None
                ),
                "cmyk": (
                    rgb_to_cmyk(hex_to_rgb(services.palette_service.pantone_provider.get_by_code(m.code).hex))
                    if services.palette_service.pantone_provider.get_by_code(m.code)
                    and services.palette_service.pantone_provider.get_by_code(m.code).hex
                    else None
                ),
                "lab": (
                    (
                        round(services.palette_service.pantone_provider.get_by_code(m.code).lab[0], 2),
                        round(services.palette_service.pantone_provider.get_by_code(m.code).lab[1], 2),
                        round(services.palette_service.pantone_provider.get_by_code(m.code).lab[2], 2),
                    )
                    if services.palette_service.pantone_provider.get_by_code(m.code)
                    else None
                ),
                "delta_e00": round(m.delta_e00, 2),
            }
            for m in matches
        ],
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
    return templates.TemplateResponse(request, "index.html", {"request": request, "defaults": defaults})


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

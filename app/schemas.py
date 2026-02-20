from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GeneratePaletteRequest(BaseModel):
    season: Literal["SS", "FW", "none"]
    audience: Literal["mass", "middle", "premium", "none"]
    style: Literal["minimal", "street", "romantic", "classic", "sport", "none"]
    geography: str = Field(min_length=1, max_length=32)
    key_color_mode: Literal["hex", "rgb", "cmyk", "lab", "tcx_code", "tcx_name"] | None = None
    key_color_value: str | None = None
    key_color_role: Literal["accent", "base"] | None = "accent"
    key_color: str | None = None
    seed: int | None = None
    count: int = Field(default=6, ge=5, le=7)

    @field_validator("key_color")
    @classmethod
    def validate_key_color(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("key_color must be in #RRGGBB format")
        int(value[1:], 16)
        return value.upper()

    @field_validator("key_color_value")
    @classmethod
    def validate_key_color_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def validate_key_color_inputs(self) -> "GeneratePaletteRequest":
        if self.key_color_mode and not self.key_color_value:
            raise ValueError("key_color_value is required when key_color_mode is set")
        return self


class PantoneMatchModel(BaseModel):
    code: str
    name: str
    hex: str | None = None
    rgb: tuple[int, int, int] | None = None
    cmyk: tuple[float, float, float, float] | None = None
    lab: tuple[float, float, float] | None = None
    delta_e00: float


class PaletteColorModel(BaseModel):
    role: str
    percent: int
    hex: str
    rgb: tuple[int, int, int]
    cmyk: tuple[float, float, float, float]
    lab: tuple[float, float, float]
    pantone_matches: list[PantoneMatchModel]


class PaletteChecksModel(BaseModel):
    pairwise_delta_e00: list[list[float]]
    min_delta_e00: float
    warnings: list[str]


class PaletteResponse(BaseModel):
    id: str
    input: GeneratePaletteRequest
    palette: list[PaletteColorModel]
    checks: PaletteChecksModel
    created_at: datetime


class HealthResponse(BaseModel):
    status: str


class MatchColorRequest(BaseModel):
    hex: str
    k: int = Field(default=3, ge=1, le=10)

    @field_validator("hex")
    @classmethod
    def validate_hex(cls, value: str) -> str:
        v = value.strip().upper()
        if len(v) != 7 or not v.startswith("#"):
            raise ValueError("hex must be in #RRGGBB format")
        int(v[1:], 16)
        return v


class MatchColorResponse(BaseModel):
    hex: str
    rgb: tuple[int, int, int]
    lab: tuple[float, float, float]
    tcx_matches: list[PantoneMatchModel]


class ConvertColorRequest(BaseModel):
    input_mode: Literal["auto", "hex", "rgb", "cmyk", "lab", "tcx_code", "tcx_name"] = "auto"
    value: str = Field(min_length=1, max_length=128)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("value is required")
        return trimmed


class ConvertColorResponse(BaseModel):
    input_mode: str
    resolved_mode: Literal["hex", "rgb", "cmyk", "lab", "tcx_code", "tcx_name"]
    value: str
    hex: str
    rgb: tuple[int, int, int]
    cmyk: tuple[float, float, float, float]
    lab: tuple[float, float, float]
    tcx_match: PantoneMatchModel | None = None


class DonateCreatePaymentRequest(BaseModel):
    amount: float = Field(ge=10.0, le=500000.0)


class DonateCreatePaymentResponse(BaseModel):
    payment_id: str
    confirmation_token: str
    amount: float
    currency: str
    return_url: str

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas import GeneratePaletteRequest
from app.services.color_math import (
    clamp,
    cmyk_to_rgb,
    delta_e00,
    hex_to_lab,
    hex_to_rgb,
    rgb_to_lab,
    lab_to_hex,
    lab_to_lch,
    lch_to_lab,
    pairwise_delta_e00_matrix,
    rgb_to_cmyk,
    rgb_to_hex,
)
from app.services.pantone_provider import ColorLibraryProvider


@dataclass(frozen=True)
class RoleSpec:
    role: str
    percent: int


@dataclass(frozen=True)
class ResolvedKeyColor:
    lab: tuple[float, float, float]
    locked_hex: str | None = None


class PaletteService:
    def __init__(self, pantone_provider: ColorLibraryProvider, max_iter: int = 20) -> None:
        self.pantone_provider = pantone_provider
        self.max_iter = max_iter

    def generate(self, request: GeneratePaletteRequest) -> dict:
        role_specs = self._role_distribution(request.count)
        base_seed = self._seed_from_request(request)
        resolved_key = self._resolve_key_color(request)
        key_role = request.key_color_role or "accent"
        key_index = self._resolve_key_index(role_specs, key_role) if resolved_key else None

        best_payload: dict | None = None
        for attempt in range(self.max_iter):
            rng = random.Random(base_seed + attempt)
            palette_labs = self._generate_labs(request, role_specs, rng, resolved_key, key_index)
            payload = self._build_payload(
                request,
                role_specs,
                palette_labs,
                resolved_key.locked_hex if resolved_key else None,
                key_index,
            )

            if payload["checks"]["min_delta_e00"] >= 5.0:
                return payload
            best_payload = payload

        if best_payload is None:
            raise RuntimeError("Failed to generate palette")

        best_payload["checks"]["warnings"].append(
            "Достигнут лимит итераций, найдены близкие цвета (ΔE00 < 5)."
        )
        return best_payload

    def _role_distribution(self, count: int) -> list[RoleSpec]:
        if count == 5:
            specs = [
                RoleSpec("accent", 14),
                RoleSpec("supporting", 20),
                RoleSpec("base", 23),
                RoleSpec("base", 23),
                RoleSpec("neutral", 20),
            ]
        elif count == 7:
            specs = [
                RoleSpec("accent", 12),
                RoleSpec("supporting", 12),
                RoleSpec("supporting", 12),
                RoleSpec("base", 18),
                RoleSpec("base", 18),
                RoleSpec("neutral", 14),
                RoleSpec("neutral", 14),
            ]
        else:
            specs = [
                RoleSpec("accent", 12),
                RoleSpec("supporting", 14),
                RoleSpec("supporting", 14),
                RoleSpec("base", 20),
                RoleSpec("base", 20),
                RoleSpec("neutral", 20),
            ]

        total = sum(x.percent for x in specs)
        if total != 100:
            normalized: list[RoleSpec] = []
            running = 0
            for idx, item in enumerate(specs):
                if idx == len(specs) - 1:
                    p = 100 - running
                else:
                    p = round(item.percent / total * 100)
                    running += p
                normalized.append(RoleSpec(item.role, p))
            return normalized
        return specs

    def _seed_from_request(self, request: GeneratePaletteRequest) -> int:
        if request.seed is not None:
            return int(request.seed)
        # Default behavior: produce a new palette on each request.
        return secrets.randbits(48)

    def _season_l_range(self, season: str, role: str) -> tuple[float, float]:
        if season == "SS":
            ranges = {
                "accent": (50, 72),
                "supporting": (48, 75),
                "base": (52, 78),
                "neutral": (75, 95),
            }
        elif season == "FW":
            ranges = {
                "accent": (35, 58),
                "supporting": (36, 60),
                "base": (35, 58),
                "neutral": (35, 62),
            }
        else:  # none
            ranges = {
                "accent": (42, 68),
                "supporting": (42, 68),
                "base": (44, 70),
                "neutral": (60, 88),
            }
        return ranges[role]

    def _audience_chroma_factor(self, audience: str) -> float:
        return {"mass": 1.0, "middle": 0.85, "premium": 0.72, "none": 0.9}[audience]

    def _style_hue_spread(self, style: str) -> float:
        return {
            "minimal": 18.0,
            "street": 75.0,
            "romantic": 32.0,
            "classic": 24.0,
            "sport": 50.0,
            "none": 36.0,
        }[style]

    @staticmethod
    def _resolve_key_index(role_specs: list[RoleSpec], key_role: str) -> int:
        for idx, spec in enumerate(role_specs):
            if spec.role == key_role:
                return idx
        return 0

    @staticmethod
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

    def _resolve_key_color(self, request: GeneratePaletteRequest) -> ResolvedKeyColor | None:
        if request.key_color:
            hex_value = request.key_color.upper()
            return ResolvedKeyColor(lab=hex_to_lab(hex_value), locked_hex=hex_value)

        mode = request.key_color_mode
        value = request.key_color_value
        if not mode or not value:
            return None

        mode = mode.lower()
        if mode == "hex":
            hex_value = value.upper()
            return ResolvedKeyColor(lab=hex_to_lab(hex_value), locked_hex=hex_value)
        if mode == "rgb":
            comps = self._parse_number_list(value, expected_len=3)
            rgb = (round(clamp(comps[0], 0, 255)), round(clamp(comps[1], 0, 255)), round(clamp(comps[2], 0, 255)))
            hex_value = rgb_to_hex(rgb)
            return ResolvedKeyColor(lab=rgb_to_lab(rgb), locked_hex=hex_value)
        if mode == "cmyk":
            comps = self._parse_number_list(value, expected_len=4)
            rgb = cmyk_to_rgb((comps[0], comps[1], comps[2], comps[3]))
            hex_value = rgb_to_hex(rgb)
            return ResolvedKeyColor(lab=rgb_to_lab(rgb), locked_hex=hex_value)
        if mode == "lab":
            comps = self._parse_number_list(value, expected_len=3)
            l = clamp(comps[0], 0, 100)
            a = clamp(comps[1], -128, 128)
            b = clamp(comps[2], -128, 128)
            return ResolvedKeyColor(lab=(l, a, b), locked_hex=None)
        if mode in {"tcx_code", "tcx_name"}:
            query = value.strip().lower()
            for entry in self.pantone_provider.list_entries():
                if mode == "tcx_code" and entry.code.strip().lower() == query:
                    if entry.hex:
                        hex_value = entry.hex.upper()
                        return ResolvedKeyColor(lab=hex_to_lab(hex_value), locked_hex=hex_value)
                    return ResolvedKeyColor(lab=entry.lab, locked_hex=None)
                if mode == "tcx_name" and entry.name.strip().lower() == query:
                    if entry.hex:
                        hex_value = entry.hex.upper()
                        return ResolvedKeyColor(lab=hex_to_lab(hex_value), locked_hex=hex_value)
                    return ResolvedKeyColor(lab=entry.lab, locked_hex=None)
            raise ValueError(f"TCX color not found for {mode}: {value}")

        raise ValueError(f"Unsupported key_color_mode: {mode}")

    def _generate_labs(
        self,
        request: GeneratePaletteRequest,
        role_specs: list[RoleSpec],
        rng: random.Random,
        resolved_key: ResolvedKeyColor | None,
        key_index: int | None,
    ) -> list[tuple[float, float, float]]:
        chroma_factor = self._audience_chroma_factor(request.audience)
        style_spread = self._style_hue_spread(request.style)

        accent_lab: tuple[float, float, float]
        accent_lch: tuple[float, float, float]

        if resolved_key is not None and key_index == 0:
            accent_lab = resolved_key.lab
            l, c, h = lab_to_lch(accent_lab)
            accent_lch = (l, c, h)
        else:
            lmin, lmax = self._season_l_range(request.season, "accent")
            l = rng.uniform(lmin, lmax)
            c = rng.uniform(42, 72) * chroma_factor
            h = rng.uniform(0, 360)
            accent_lch = (l, c, h)
            accent_lab = lch_to_lab(accent_lch)

        anchor_lch = accent_lch
        if resolved_key is not None and key_index is not None and key_index != 0:
            anchor_lch = lab_to_lch(resolved_key.lab)

        labs = [accent_lab]

        for spec in role_specs[1:]:
            al, ac, ah = anchor_lch
            if spec.role == "supporting":
                sign = -1 if rng.random() < 0.5 else 1
                hue_shift = rng.uniform(20, 40) + style_spread * 0.15
                h = (ah + sign * hue_shift) % 360
                c = clamp(ac * rng.uniform(0.55, 0.8), 8, 95)
                lmin, lmax = self._season_l_range(request.season, "supporting")
                l = clamp(al + rng.uniform(-8, 8), lmin, lmax)
            elif spec.role == "base":
                sign = -1 if rng.random() < 0.5 else 1
                hue_shift = rng.uniform(5, 24) + style_spread * 0.08
                h = (ah + sign * hue_shift) % 360
                c = clamp(ac * rng.uniform(0.25, 0.48), 4, 55)
                lmin, lmax = self._season_l_range(request.season, "base")
                l = rng.uniform(lmin, lmax)
            else:  # neutral
                h = ah
                c = rng.uniform(1.0, 8.0)
                lmin, lmax = self._season_l_range(request.season, "neutral")
                l = rng.uniform(lmin, lmax)

            labs.append(lch_to_lab((l, c, h)))

        if resolved_key is not None and key_index is not None:
            labs[key_index] = resolved_key.lab
        return labs

    def _build_payload(
        self,
        request: GeneratePaletteRequest,
        role_specs: list[RoleSpec],
        labs: list[tuple[float, float, float]],
        locked_key_hex: str | None,
        key_index: int | None,
    ) -> dict:
        matrix = pairwise_delta_e00_matrix(labs)
        rounded_matrix = [[round(x, 2) for x in row] for row in matrix]

        min_delta = 999.0
        n = len(labs)
        for i in range(n):
            for j in range(i + 1, n):
                min_delta = min(min_delta, matrix[i][j])

        warnings: list[str] = []
        if min_delta < 5.0:
            warnings.append("Есть близкие пары цветов (ΔE00 < 5).")

        # Base compatibility: mean DeltaE to others in [10..40].
        for idx, spec in enumerate(role_specs):
            if spec.role != "base":
                continue
            deltas = [matrix[idx][j] for j in range(len(role_specs)) if j != idx]
            avg_d = sum(deltas) / len(deltas)
            if avg_d < 10 or avg_d > 40:
                warnings.append(
                    f"Базовый цвет #{idx + 1} имеет средний ΔE00={avg_d:.2f} вне рекомендуемого диапазона [10..40]."
                )

        # Lightness contrast warning
        for i in range(n):
            for j in range(i + 1, n):
                l_diff = abs(labs[i][0] - labs[j][0])
                if l_diff < 6:
                    warnings.append("Есть пары со слабым контрастом по L* (< 6).")
                    i = n
                    break

        palette: list[dict] = []
        for idx, spec in enumerate(role_specs):
            lab = labs[idx]
            if key_index is not None and idx == key_index and locked_key_hex:
                hex_color = locked_key_hex
                lab = rgb_to_lab(hex_to_rgb(hex_color))
            else:
                hex_color = lab_to_hex(lab)
            rgb = hex_to_rgb(hex_color)
            cmyk = rgb_to_cmyk(rgb)
            matches = self.pantone_provider.match_top_k(lab, k=3)

            palette.append(
                {
                    "role": spec.role,
                    "percent": spec.percent,
                    "hex": hex_color,
                    "rgb": rgb,
                    "cmyk": cmyk,
                    "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
                    "pantone_matches": [
                        (
                            lambda entry: {
                            "code": m.code,
                            "name": m.name,
                            "hex": entry.hex if entry else None,
                            "rgb": hex_to_rgb(entry.hex) if entry and entry.hex else None,
                            "cmyk": rgb_to_cmyk(hex_to_rgb(entry.hex)) if entry and entry.hex else None,
                            "lab": (
                                (round(entry.lab[0], 2), round(entry.lab[1], 2), round(entry.lab[2], 2))
                                if entry
                                else None
                            ),
                            "delta_e00": round(m.delta_e00, 2),
                        }
                        )(self.pantone_provider.get_by_code(m.code))
                        for m in matches
                    ],
                }
            )

        return {
            "input": request.model_dump(),
            "palette": palette,
            "checks": {
                "pairwise_delta_e00": rounded_matrix,
                "min_delta_e00": round(min_delta, 2),
                "warnings": sorted(set(warnings)),
            },
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

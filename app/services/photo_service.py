from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.services.color_math import rgb_to_cmyk, rgb_to_hex, rgb_to_lab
from app.services.pantone_provider import ColorLibraryProvider


class PhotoTcxService:
    def __init__(self, provider: ColorLibraryProvider) -> None:
        self.provider = provider

    def analyze(self, image_bytes: bytes, count: int = 6) -> dict:
        if not image_bytes:
            raise ValueError("Empty image payload")

        count = max(1, min(int(count), 12))

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise ValueError("Invalid image format") from exc

        image.thumbnail((600, 600))
        quantized = image.quantize(colors=count, method=Image.MEDIANCUT)
        palette = quantized.getpalette() or []
        color_counts = quantized.getcolors() or []

        total_pixels = sum(cnt for cnt, _ in color_counts) or 1
        color_rows: list[dict] = []

        for cnt, palette_index in sorted(color_counts, key=lambda x: x[0], reverse=True)[:count]:
            base = palette_index * 3
            if base + 2 >= len(palette):
                continue
            rgb = (palette[base], palette[base + 1], palette[base + 2])
            hex_color = rgb_to_hex(rgb)
            lab = rgb_to_lab(rgb)
            matches = self.provider.match_top_k(lab, k=3)

            match_rows = []
            for m in matches:
                entry = self.provider.get_by_code(m.code)
                match_rows.append(
                    {
                        "code": m.code,
                        "name": m.name,
                        "hex": entry.hex if entry else None,
                        "rgb": None,
                        "cmyk": None,
                        "lab": (
                            (round(entry.lab[0], 2), round(entry.lab[1], 2), round(entry.lab[2], 2))
                            if entry
                            else None
                        ),
                        "delta_e00": round(m.delta_e00, 2),
                    }
                )
                if entry and entry.hex:
                    mrgb = tuple(int(entry.hex[i:i + 2], 16) for i in (1, 3, 5))
                    match_rows[-1]["rgb"] = mrgb
                    match_rows[-1]["cmyk"] = rgb_to_cmyk(mrgb)

            color_rows.append(
                {
                    "percent": round(cnt / total_pixels * 100, 2),
                    "hex": hex_color,
                    "rgb": rgb,
                    "cmyk": rgb_to_cmyk(rgb),
                    "lab": (round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)),
                    "tcx_matches": match_rows,
                }
            )

        color_rows.sort(key=lambda x: x["percent"], reverse=True)
        return {
            "count": len(color_rows),
            "colors": color_rows,
        }

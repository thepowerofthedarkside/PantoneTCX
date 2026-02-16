from pathlib import Path

from app.schemas import GeneratePaletteRequest
from app.services.palette_service import PaletteService
from app.services.pantone_provider import CsvPantoneProvider, SqliteTcxProvider


DATA = Path(__file__).resolve().parents[1] / "data" / "pantone_stub.csv"
TCX_DB = Path(__file__).resolve().parents[1] / "paleton_tcx.sqlite3"


def _service() -> PaletteService:
    if TCX_DB.exists():
        return PaletteService(SqliteTcxProvider(TCX_DB))
    return PaletteService(CsvPantoneProvider(DATA))


def _request() -> GeneratePaletteRequest:
    return GeneratePaletteRequest(
        season="SS",
        audience="mass",
        style="street",
        geography="EU",
        key_color="#D26C31",
        count=6,
    )


def test_generate_returns_requested_count_and_roles():
    result = _service().generate(_request())
    assert len(result["palette"]) == 6
    roles = [x["role"] for x in result["palette"]]
    assert roles.count("accent") == 1
    assert roles.count("supporting") == 2
    assert roles.count("base") == 2
    assert roles.count("neutral") == 1


def test_percent_sum_to_100():
    result = _service().generate(_request())
    assert sum(x["percent"] for x in result["palette"]) == 100


def test_min_delta_threshold_is_respected():
    result = _service().generate(_request())
    assert result["checks"]["min_delta_e00"] >= 5.0


def test_key_color_used_as_accent_anchor():
    result = _service().generate(_request())
    accent = result["palette"][0]
    assert accent["role"] == "accent"
    assert accent["hex"].startswith("#")


def test_key_color_accepts_tcx_code():
    request = _request().model_copy(
        update={"key_color": None, "key_color_mode": "tcx_code", "key_color_value": "17-0836"}
    )
    result = _service().generate(request)
    assert result["palette"][0]["role"] == "accent"
    assert len(result["palette"][0]["pantone_matches"]) >= 1


def test_key_color_accepts_tcx_name():
    request = _request().model_copy(
        update={"key_color": None, "key_color_mode": "tcx_name", "key_color_value": "Ecru Olive"}
    )
    result = _service().generate(request)
    assert result["palette"][0]["role"] == "accent"
    assert len(result["palette"][0]["pantone_matches"]) >= 1


def test_key_color_can_be_base_role():
    request = _request().model_copy(
        update={
            "key_color": None,
            "key_color_mode": "tcx_code",
            "key_color_value": "17-0836",
            "key_color_role": "base",
        }
    )
    result = _service().generate(request)
    base_items = [x for x in result["palette"] if x["role"] == "base"]
    assert any(x["hex"] == "#927B3C" for x in base_items)


def test_none_values_are_supported():
    request = _request().model_copy(update={"season": "none", "audience": "none", "style": "none"})
    result = _service().generate(request)
    assert len(result["palette"]) == 6

from app.services.color_math import (
    delta_e00,
    hex_to_rgb,
    pairwise_delta_e00_matrix,
    rgb_to_cmyk,
    rgb_to_hex,
    rgb_to_lab,
)


def test_hex_roundtrip():
    rgb = hex_to_rgb("#D26C31")
    assert rgb_to_hex(rgb) == "#D26C31"


def test_rgb_to_lab_range():
    l, a, b = rgb_to_lab((210, 108, 49))
    assert 0 <= l <= 100
    assert -128 <= a <= 128
    assert -128 <= b <= 128


def test_delta_e00_zero_for_same_color():
    lab = rgb_to_lab((100, 120, 130))
    assert delta_e00(lab, lab) == 0


def test_delta_e00_symmetry():
    lab1 = rgb_to_lab((255, 0, 0))
    lab2 = rgb_to_lab((0, 0, 255))
    d12 = delta_e00(lab1, lab2)
    d21 = delta_e00(lab2, lab1)
    assert abs(d12 - d21) < 1e-9


def test_pairwise_matrix_shape_and_diag():
    labs = [rgb_to_lab((10, 10, 10)), rgb_to_lab((20, 20, 20)), rgb_to_lab((30, 30, 30))]
    m = pairwise_delta_e00_matrix(labs)
    assert len(m) == 3
    assert len(m[0]) == 3
    assert m[0][0] == 0


def test_rgb_to_cmyk_black():
    assert rgb_to_cmyk((0, 0, 0)) == (0.0, 0.0, 0.0, 100.0)

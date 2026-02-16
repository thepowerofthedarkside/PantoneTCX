from __future__ import annotations

from math import atan2, cos, degrees, exp, radians, sin, sqrt


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip()
    if not value.startswith("#"):
        raise ValueError("HEX must start with #")
    value = value[1:]
    if len(value) != 6:
        raise ValueError("HEX must be in #RRGGBB format")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (x / 255.0 for x in rgb)
    r_lin = _srgb_to_linear(r)
    g_lin = _srgb_to_linear(g)
    b_lin = _srgb_to_linear(b)

    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    xn, yn, zn = 0.95047, 1.0, 1.08883
    xr, yr, zr = x / xn, y / yn, z / zn

    def f(t: float) -> float:
        delta = 6 / 29
        return t ** (1 / 3) if t > delta**3 else t / (3 * delta**2) + 4 / 29

    fx, fy, fz = f(xr), f(yr), f(zr)
    l = 116 * fy - 16
    a = 500 * (fx - fy)
    b2 = 200 * (fy - fz)
    return l, a, b2


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    l, a, b = lab
    fy = (l + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def invf(t: float) -> float:
        delta = 6 / 29
        return t**3 if t > delta else 3 * (delta**2) * (t - 4 / 29)

    xn, yn, zn = 0.95047, 1.0, 1.08883
    x = xn * invf(fx)
    y = yn * invf(fy)
    z = zn * invf(fz)

    r_lin = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
    g_lin = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
    b_lin = x * 0.0556434 + y * -0.2040259 + z * 1.0572252

    r = clamp(_linear_to_srgb(r_lin), 0.0, 1.0)
    g = clamp(_linear_to_srgb(g_lin), 0.0, 1.0)
    b2 = clamp(_linear_to_srgb(b_lin), 0.0, 1.0)

    return round(r * 255), round(g * 255), round(b2 * 255)


def lab_to_lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    l, a, b = lab
    c = sqrt(a * a + b * b)
    h = degrees(atan2(b, a)) % 360.0
    return l, c, h


def lch_to_lab(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    l, c, h = lch
    hr = radians(h)
    a = c * cos(hr)
    b = c * sin(hr)
    return l, a, b


def hex_to_lab(hex_color: str) -> tuple[float, float, float]:
    return rgb_to_lab(hex_to_rgb(hex_color))


def lab_to_hex(lab: tuple[float, float, float]) -> str:
    return rgb_to_hex(lab_to_rgb(lab))


def rgb_to_cmyk(rgb: tuple[int, int, int]) -> tuple[float, float, float, float]:
    r, g, b = (x / 255.0 for x in rgb)
    k = 1 - max(r, g, b)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 100.0
    c = (1 - r - k) / (1 - k)
    m = (1 - g - k) / (1 - k)
    y = (1 - b - k) / (1 - k)
    return round(c * 100, 2), round(m * 100, 2), round(y * 100, 2), round(k * 100, 2)


def cmyk_to_rgb(cmyk: tuple[float, float, float, float]) -> tuple[int, int, int]:
    c, m, y, k = cmyk
    c = clamp(c, 0.0, 100.0) / 100.0
    m = clamp(m, 0.0, 100.0) / 100.0
    y = clamp(y, 0.0, 100.0) / 100.0
    k = clamp(k, 0.0, 100.0) / 100.0
    r = round(255 * (1 - c) * (1 - k))
    g = round(255 * (1 - m) * (1 - k))
    b = round(255 * (1 - y) * (1 - k))
    return r, g, b


def delta_e00(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = sqrt(a1 * a1 + b1 * b1)
    c2 = sqrt(a2 * a2 + b2 * b2)
    c_bar = (c1 + c2) / 2

    g = 0.5 * (1 - sqrt((c_bar**7) / (c_bar**7 + 25**7)))

    a1p = (1 + g) * a1
    a2p = (1 + g) * a2
    c1p = sqrt(a1p * a1p + b1 * b1)
    c2p = sqrt(a2p * a2p + b2 * b2)

    h1p = degrees(atan2(b1, a1p)) % 360
    h2p = degrees(atan2(b2, a2p)) % 360

    dl = l2 - l1
    dc = c2p - c1p

    if c1p * c2p == 0:
        dh = 0.0
    else:
        dh_raw = h2p - h1p
        if dh_raw > 180:
            dh_raw -= 360
        elif dh_raw < -180:
            dh_raw += 360
        dh = dh_raw

    d_hp = 2 * sqrt(c1p * c2p) * sin(radians(dh / 2))

    l_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2

    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    else:
        hsum = h1p + h2p
        if abs(h1p - h2p) > 180:
            hp_bar = (hsum + 360) / 2 if hsum < 360 else (hsum - 360) / 2
        else:
            hp_bar = hsum / 2

    t = (
        1
        - 0.17 * cos(radians(hp_bar - 30))
        + 0.24 * cos(radians(2 * hp_bar))
        + 0.32 * cos(radians(3 * hp_bar + 6))
        - 0.20 * cos(radians(4 * hp_bar - 63))
    )

    delta_ro = 30 * exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * sqrt((cp_bar**7) / (cp_bar**7 + 25**7))

    sl = 1 + (0.015 * ((l_bar - 50) ** 2)) / sqrt(20 + ((l_bar - 50) ** 2))
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t

    rt = -sin(radians(2 * delta_ro)) * rc

    kl = kc = kh = 1.0
    de = sqrt(
        (dl / (kl * sl)) ** 2
        + (dc / (kc * sc)) ** 2
        + (d_hp / (kh * sh)) ** 2
        + rt * (dc / (kc * sc)) * (d_hp / (kh * sh))
    )
    return float(abs(de))


def pairwise_delta_e00_matrix(labs: list[tuple[float, float, float]]) -> list[list[float]]:
    n = len(labs)
    matrix = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = delta_e00(labs[i], labs[j])
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix

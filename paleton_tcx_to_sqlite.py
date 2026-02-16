# paleton_tcx_to_sqlite.py
# pip install requests beautifulsoup4
#
# Usage:
#   python paleton_tcx_to_sqlite.py --db paleton_tcx.sqlite3
#   python paleton_tcx_to_sqlite.py --db paleton_tcx.sqlite3 --max-pages 3
#
# What it does:
# - Crawls https://www.paleton.net/brand/24-pantone/16-fhi-cotton-tcx/?page=N
# - Extracts: TCX code, name, HEX
# - Saves into SQLite with UPSERT

import argparse
import re
import sqlite3
import time
from math import pow
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL_DEFAULT = "https://www.paleton.net/brand/24-pantone/16-fhi-cotton-tcx/"

TCX_RE = re.compile(r"\b(\d{2}-\d{4})\s*TCX\b", re.IGNORECASE)
HEX_RE = re.compile(r"#([0-9A-Fa-f]{6})\b")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hex_to_lab_string(hex_value: str) -> str:
    """
    Convert '#RRGGBB' to CIE L*a*b* (D65/2°), stored as 'L,a,b' with 2 decimals.
    """
    if not hex_value:
        return ""

    m = HEX_RE.search(hex_value)
    if not m:
        return ""

    hex_clean = m.group(1)
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0

    def srgb_to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)

    r_lin = srgb_to_linear(r)
    g_lin = srgb_to_linear(g)
    b_lin = srgb_to_linear(b)

    # linear RGB -> XYZ (D65)
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # XYZ reference white (D65)
    xn, yn, zn = 0.95047, 1.0, 1.08883
    xr, yr, zr = x / xn, y / yn, z / zn

    def f(t: float) -> float:
        delta = 6 / 29
        return pow(t, 1 / 3) if t > delta**3 else (t / (3 * delta**2)) + (4 / 29)

    fx = f(xr)
    fy = f(yr)
    fz = f(zr)

    l = 116 * fy - 16
    a = 500 * (fx - fy)
    b2 = 200 * (fy - fz)
    return f"{l:.2f},{a:.2f},{b2:.2f}"


def get_soup(url: str) -> BeautifulSoup:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TCXScraper/1.0; +local)",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    r = requests.get(url, headers=headers, timeout=45)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def detect_max_page(soup: BeautifulSoup, base_url: str) -> int:
    max_page = 1
    for a in soup.select('a[href*="?page="]'):
        href = a.get("href", "")
        full = urljoin(base_url, href)
        q = parse_qs(urlparse(full).query)
        if "page" in q:
            try:
                n = int(q["page"][0])
                if n > max_page:
                    max_page = n
            except ValueError:
                pass
    return max_page


def parse_page_items(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """
    Parse one catalog page and extract TCX code, name, HEX and LAB.
    """
    rows: list[dict] = []

    # Primary strategy: each color card is in div.list
    for block in soup.select("div.list"):
        h2 = block.find("h2")
        if not h2:
            continue

        txt = h2.get_text(" ", strip=True)
        m = TCX_RE.search(txt)
        if not m:
            continue

        code = m.group(1)

        h3 = block.find("h3")
        name = h3.get_text(" ", strip=True) if h3 else ""
        if TCX_RE.search(name):
            name = ""

        block_text = block.get_text(" ", strip=True)
        mh = HEX_RE.search(block_text or "")
        if not mh:
            # Sometimes HEX is only in style attributes.
            mh = HEX_RE.search(str(block))
        hex_value = f"#{mh.group(1).upper()}" if mh else ""

        rows.append(
            {
                "tcx_code": code,
                "name": name,
                "hex": hex_value,
                "lab": hex_to_lab_string(hex_value),
                "source_url": page_url,
            }
        )

    # Fallback for unexpected layouts: old DOM-walk strategy.
    if not rows:
        for h2 in soup.find_all(["h2", "h3", "h4"]):
            txt = h2.get_text(" ", strip=True)
            m = TCX_RE.search(txt)
            if not m:
                continue

            code = m.group(1)

            name = None
            nxt = h2.find_next(["h3", "h4"])
            if nxt:
                name_txt = nxt.get_text(" ", strip=True)
                if name_txt and not TCX_RE.search(name_txt):
                    name = name_txt

            hex_value = None
            probe = h2
            for _ in range(12):
                probe = probe.find_next()
                if not probe:
                    break
                t = probe.get_text(" ", strip=True) if hasattr(probe, "get_text") else ""
                mh = HEX_RE.search(t or "")
                if mh:
                    hex_value = f"#{mh.group(1).upper()}"
                    break
                if t and TCX_RE.search(t) and probe.name in {"h2", "h3", "h4"}:
                    break

            if not name:
                name = ""

            rows.append(
                {
                    "tcx_code": code,
                    "name": name,
                    "hex": hex_value or "",
                    "lab": hex_to_lab_string(hex_value or ""),
                    "source_url": page_url,
                }
            )

    # Deduplicate inside one page.
    uniq = {}
    for r in rows:
        k = r["tcx_code"]
        if k not in uniq:
            uniq[k] = r
        else:
            if (not uniq[k].get("hex") and r.get("hex")) or (not uniq[k].get("name") and r.get("name")):
                uniq[k] = r

    return list(uniq.values())


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tcx_colors (
            tcx_code   TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            hex        TEXT NOT NULL,
            lab        TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL,
            scraped_at TEXT NOT NULL
        );
        """
    )
    # Migration for existing databases without the LAB column.
    cols = [row[1].lower() for row in conn.execute("PRAGMA table_info(tcx_colors);").fetchall()]
    if "lab" not in cols:
        conn.execute("ALTER TABLE tcx_colors ADD COLUMN lab TEXT NOT NULL DEFAULT '';")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tcx_colors_hex ON tcx_colors(hex);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tcx_colors_name ON tcx_colors(name);")
    conn.commit()


def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    now = utc_now_iso()
    cur = conn.cursor()
    n = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO tcx_colors (tcx_code, name, hex, lab, source_url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tcx_code) DO UPDATE SET
                name=excluded.name,
                hex=excluded.hex,
                lab=excluded.lab,
                source_url=excluded.source_url,
                scraped_at=excluded.scraped_at
            """,
            (r["tcx_code"], r["name"], r["hex"], r["lab"], r["source_url"], now),
        )
        n += 1
    conn.commit()
    return n


def backfill_missing_lab(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("SELECT tcx_code, hex FROM tcx_colors WHERE IFNULL(lab, '') = '';")
    updates = []
    for tcx_code, hex_value in cur.fetchall():
        lab = hex_to_lab_string(hex_value or "")
        if lab:
            updates.append((lab, tcx_code))

    if updates:
        cur.executemany("UPDATE tcx_colors SET lab = ? WHERE tcx_code = ?;", updates)
        conn.commit()
    return len(updates)


def crawl_to_sqlite(
    db_path: str,
    base_url: str,
    delay_sec: float,
    max_pages: int | None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        backfilled = backfill_missing_lab(conn)
        if backfilled:
            print(f"Backfilled LAB for existing rows: {backfilled}")

        soup1 = get_soup(base_url)
        detected_max = detect_max_page(soup1, base_url)
        total_pages = detected_max if max_pages is None else min(max_pages, detected_max)

        total_saved = 0
        total_seen = 0

        for page in range(1, total_pages + 1):
            url = base_url if page == 1 else f"{base_url}?page={page}"
            soup = soup1 if page == 1 else get_soup(url)

            rows = parse_page_items(soup, url)
            total_seen += len(rows)

            saved = upsert_rows(conn, rows)
            total_saved += saved

            print(f"[{page}/{total_pages}] parsed={len(rows)} upserted={saved} url={url}")

            if page != total_pages:
                time.sleep(delay_sec)

        print(f"Done. pages={total_pages} parsed_total={total_seen} upserted_total={total_saved} db={db_path}")

    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="Path to SQLite DB (will be created if not exists)")
    p.add_argument("--base-url", default=BASE_URL_DEFAULT, help="Base catalog URL")
    p.add_argument("--delay", type=float, default=0.7, help="Delay between requests (seconds)")
    p.add_argument("--max-pages", type=int, default=None, help="Limit pages for test runs")
    args = p.parse_args()

    crawl_to_sqlite(
        db_path=args.db,
        base_url=args.base_url,
        delay_sec=args.delay,
        max_pages=args.max_pages,
    )

if __name__ == "__main__":
    main()

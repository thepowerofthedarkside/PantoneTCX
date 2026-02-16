from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.color_math import delta_e00, hex_to_lab


@dataclass(frozen=True)
class ColorLibraryEntry:
    code: str
    name: str
    lab: tuple[float, float, float]
    hex: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ColorMatch:
    code: str
    name: str
    delta_e00: float


class ColorLibraryProvider(Protocol):
    def list_entries(self) -> list[ColorLibraryEntry]:
        ...

    def match_top_k(self, lab: tuple[float, float, float], k: int = 3) -> list[ColorMatch]:
        ...

    def get_by_code(self, code: str) -> ColorLibraryEntry | None:
        ...

    def get_by_name(self, name: str) -> ColorLibraryEntry | None:
        ...


class CsvPantoneProvider:
    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self._entries: list[ColorLibraryEntry] = []
        self._by_code: dict[str, ColorLibraryEntry] = {}
        self._by_name: dict[str, ColorLibraryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Pantone stub file not found: {self.csv_path}")

        entries: list[ColorLibraryEntry] = []
        with self.csv_path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                code = normalized.get("code", "")
                name = normalized.get("name", "")
                l = float(normalized.get("l", 0.0))
                a = float(normalized.get("a", 0.0))
                b = float(normalized.get("b", 0.0))
                if code and name:
                    entries.append(ColorLibraryEntry(code=code, name=name, lab=(l, a, b), hex=None))
        self._entries = entries
        self._by_code = {e.code.strip().lower(): e for e in entries}
        self._by_name = {e.name.strip().lower(): e for e in entries}

    def list_entries(self) -> list[ColorLibraryEntry]:
        return list(self._entries)

    def match_top_k(self, lab: tuple[float, float, float], k: int = 3) -> list[ColorMatch]:
        scored: list[ColorMatch] = []
        for entry in self._entries:
            scored.append(
                ColorMatch(
                    code=entry.code,
                    name=entry.name,
                    delta_e00=round(delta_e00(lab, entry.lab), 4),
                )
            )
        scored.sort(key=lambda x: x.delta_e00)
        return scored[:k]

    def get_by_code(self, code: str) -> ColorLibraryEntry | None:
        return self._by_code.get((code or "").strip().lower())

    def get_by_name(self, name: str) -> ColorLibraryEntry | None:
        return self._by_name.get((name or "").strip().lower())


class SqliteTcxProvider:
    """
    Color provider backed by tcx_colors table in paleton_tcx.sqlite3.
    Expected columns: tcx_code, name, hex, lab.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._entries: list[ColorLibraryEntry] = []
        self._by_code: dict[str, ColorLibraryEntry] = {}
        self._by_name: dict[str, ColorLibraryEntry] = {}
        self._load()

    @staticmethod
    def _parse_lab(lab_raw: str | None) -> tuple[float, float, float] | None:
        if not lab_raw:
            return None
        parts = [p.strip() for p in lab_raw.split(",")]
        if len(parts) != 3:
            return None
        try:
            return float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            return None

    def _load(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"TCX database not found: {self.db_path}")

        entries: list[ColorLibraryEntry] = []
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT tcx_code, name, hex, lab, source_url FROM tcx_colors WHERE tcx_code IS NOT NULL AND name IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()

        for code, name, hex_value, lab_raw, source_url in rows:
            lab = self._parse_lab(lab_raw)
            if lab is None and hex_value:
                try:
                    lab = hex_to_lab(hex_value)
                except Exception:
                    lab = None
            if not code or not name or lab is None:
                continue
            entries.append(
                ColorLibraryEntry(
                    code=str(code),
                    name=str(name),
                    lab=lab,
                    hex=str(hex_value).upper() if hex_value else None,
                    source_url=str(source_url) if source_url else None,
                )
            )

        self._entries = entries
        self._by_code = {e.code.strip().lower(): e for e in entries}
        self._by_name = {e.name.strip().lower(): e for e in entries}

    def list_entries(self) -> list[ColorLibraryEntry]:
        return list(self._entries)

    def match_top_k(self, lab: tuple[float, float, float], k: int = 3) -> list[ColorMatch]:
        scored: list[ColorMatch] = []
        for entry in self._entries:
            scored.append(
                ColorMatch(
                    code=entry.code,
                    name=entry.name,
                    delta_e00=round(delta_e00(lab, entry.lab), 4),
                )
            )
        scored.sort(key=lambda x: x.delta_e00)
        return scored[:k]

    def get_by_code(self, code: str) -> ColorLibraryEntry | None:
        return self._by_code.get((code or "").strip().lower())

    def get_by_name(self, name: str) -> ColorLibraryEntry | None:
        return self._by_name.get((name or "").strip().lower())

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class PaletteStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS palettes (
                    id TEXT PRIMARY KEY,
                    input_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save(self, input_payload: dict, result_payload: dict) -> tuple[str, datetime]:
        palette_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO palettes(id, input_json, result_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    palette_id,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(result_payload, ensure_ascii=False),
                    created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return palette_id, created_at

    def get(self, palette_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, input_json, result_json, created_at FROM palettes WHERE id = ?",
                (palette_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        return {
            "id": row[0],
            "input": json.loads(row[1]),
            "result": json.loads(row[2]),
            "created_at": row[3],
        }

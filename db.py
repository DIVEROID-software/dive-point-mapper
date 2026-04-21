"""SQLite 다이빙 포인트 DB"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "dive_points.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dive_points (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                name_en     TEXT,
                lat         REAL NOT NULL,
                lng         REAL NOT NULL,
                region      TEXT,
                country     TEXT,
                depth_max   REAL,
                difficulty  TEXT,
                description TEXT,
                source      TEXT,
                confidence  TEXT DEFAULT 'medium',
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_latlon ON dive_points(lat, lng)")
        conn.commit()


def insert_points(points: list[dict], source: str) -> int:
    """포인트 삽입 (중복 이름+좌표 skip). 삽입 건수 반환."""
    inserted = 0
    with get_conn() as conn:
        for p in points:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO dive_points
                        (name, name_en, lat, lng, region, country, depth_max, difficulty, description, source, confidence)
                    SELECT ?,?,?,?,?,?,?,?,?,?,?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dive_points
                        WHERE ABS(lat-?) < 0.001 AND ABS(lng-?) < 0.001 AND name=?
                    )
                """,
                    (
                        p.get("name", ""),
                        p.get("name_en", ""),
                        float(p["lat"]),
                        float(p["lng"]),
                        p.get("region", ""),
                        p.get("country", ""),
                        p.get("depth_max"),
                        p.get("difficulty", ""),
                        p.get("description", ""),
                        source,
                        p.get("confidence", "medium"),
                        float(p["lat"]),
                        float(p["lng"]),
                        p.get("name", ""),
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except Exception:
                continue
        conn.commit()
    return inserted


def get_all_points() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM dive_points ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dive_points").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM dive_points GROUP BY source"
        ).fetchall()
        countries = conn.execute(
            "SELECT COUNT(DISTINCT country) FROM dive_points WHERE country != ''"
        ).fetchone()[0]
    return {
        "total": total,
        "by_source": {r[0]: r[1] for r in by_source},
        "countries": countries,
    }


def update_point(point_id: int, **kwargs):
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [point_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE dive_points SET {fields} WHERE id=?", values)
        conn.commit()


def delete_point(point_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM dive_points WHERE id=?", [point_id])
        conn.commit()

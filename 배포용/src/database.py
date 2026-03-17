import sqlite3
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, ALL_COLUMNS

POWER_COLS = [f"{key}_power" for key, _ in ALL_COLUMNS]
VOLUME_COLS = [f"{key}_volume" for key, _ in ALL_COLUMNS]
ALL_DATA_COLS = POWER_COLS + VOLUME_COLS

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meter_readings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_date        TEXT NOT NULL,
    dong_bunche_power   REAL,
    dong_bunche_volume  REAL,
    dong_aekche_power   REAL,
    dong_aekche_volume  REAL,
    dong_pimak_power    REAL,
    dong_pimak_volume   REAL,
    sin_aekche_power    REAL,
    sin_aekche_volume   REAL,
    sin_yeonma_power    REAL,
    sin_yeonma_volume   REAL,
    sin_syote_power     REAL,
    sin_syote_volume    REAL,
    is_interpolated     INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(reading_date)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_readings_date ON meter_readings(reading_date);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str = DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)


def upsert_reading(
    values: dict,
    is_interpolated: bool = False,
    db_path: str = DB_PATH,
):
    """날짜별 데이터 삽입 또는 교체. values에는 reading_date + 12개 데이터 컬럼."""
    cols = ["reading_date"] + ALL_DATA_COLS + ["is_interpolated"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    row = (
        [values["reading_date"]]
        + [values.get(c) for c in ALL_DATA_COLS]
        + [1 if is_interpolated else 0]
    )
    sql = f"INSERT OR REPLACE INTO meter_readings ({col_names}) VALUES ({placeholders})"
    with get_connection(db_path) as conn:
        conn.execute(sql, row)


def get_reading(date: datetime.date, db_path: str = DB_PATH) -> dict | None:
    sql = "SELECT * FROM meter_readings WHERE reading_date = ?"
    with get_connection(db_path) as conn:
        row = conn.execute(sql, (date.isoformat(),)).fetchone()
    return dict(row) if row else None


def get_last_reading_before(date: datetime.date, db_path: str = DB_PATH) -> dict | None:
    sql = "SELECT * FROM meter_readings WHERE reading_date < ? ORDER BY reading_date DESC LIMIT 1"
    with get_connection(db_path) as conn:
        row = conn.execute(sql, (date.isoformat(),)).fetchone()
    return dict(row) if row else None


def get_readings_in_range(
    start: datetime.date,
    end: datetime.date,
    db_path: str = DB_PATH,
) -> list[dict]:
    sql = """
        SELECT * FROM meter_readings
        WHERE reading_date >= ? AND reading_date <= ?
        ORDER BY reading_date ASC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, (start.isoformat(), end.isoformat())).fetchall()
    return [dict(r) for r in rows]


def delete_reading(date: datetime.date, db_path: str = DB_PATH) -> bool:
    sql = "DELETE FROM meter_readings WHERE reading_date = ?"
    with get_connection(db_path) as conn:
        cur = conn.execute(sql, (date.isoformat(),))
    return cur.rowcount > 0


def count_readings_in_range(
    start: datetime.date,
    end: datetime.date,
    db_path: str = DB_PATH,
) -> int:
    sql = "SELECT COUNT(*) FROM meter_readings WHERE reading_date >= ? AND reading_date <= ?"
    with get_connection(db_path) as conn:
        return conn.execute(sql, (start.isoformat(), end.isoformat())).fetchone()[0]


def get_all_dates(db_path: str = DB_PATH) -> list[str]:
    sql = "SELECT reading_date FROM meter_readings ORDER BY reading_date ASC"
    with get_connection(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    return [r[0] for r in rows]

import datetime
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALL_COLUMNS

POWER_COLS = [f"{key}_power" for key, _ in ALL_COLUMNS]
VOLUME_COLS = [f"{key}_volume" for key, _ in ALL_COLUMNS]
ALL_DATA_COLS = POWER_COLS + VOLUME_COLS
TABLE = "meter_readings"


def _get_client(access_token: str = ""):
    import streamlit as st
    from supabase import create_client
    client = create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["anon_key"],
    )
    if access_token:
        client.postgrest.auth(access_token)
    return client


def init_db(**_):
    """No-op: 스키마는 Supabase 대시보드에서 관리합니다."""
    pass


def upsert_reading(
    values: dict,
    is_interpolated: bool = False,
    access_token: str = "",
    user_id: str = "",
):
    client = _get_client(access_token)
    row = {
        "user_id": user_id,
        "reading_date": values["reading_date"],
        "is_interpolated": bool(is_interpolated),
        "deleted_at": None,
        "delete_batch_id": None,
    }
    for col in ALL_DATA_COLS:
        val = values.get(col)
        row[col] = float(val) if val is not None else None
    client.table(TABLE).upsert(row, on_conflict="user_id,reading_date").execute()


def get_reading(date: datetime.date, access_token: str = "") -> dict | None:
    client = _get_client(access_token)
    res = (
        client.table(TABLE)
        .select("*")
        .eq("reading_date", date.isoformat())
        .maybe_single()
        .execute()
    )
    return res.data


def get_last_reading_before(date: datetime.date, access_token: str = "") -> dict | None:
    client = _get_client(access_token)
    res = (
        client.table(TABLE)
        .select("*")
        .lt("reading_date", date.isoformat())
        .order("reading_date", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_readings_in_range(
    start: datetime.date,
    end: datetime.date,
    access_token: str = "",
) -> list[dict]:
    client = _get_client(access_token)
    res = (
        client.table(TABLE)
        .select("*")
        .gte("reading_date", start.isoformat())
        .lte("reading_date", end.isoformat())
        .order("reading_date")
        .execute()
    )
    return res.data or []


def delete_reading(date: datetime.date, access_token: str = "") -> bool:
    client = _get_client(access_token)
    res = (
        client.table(TABLE)
        .delete()
        .eq("reading_date", date.isoformat())
        .execute()
    )
    return len(res.data) > 0


def count_readings_in_range(
    start: datetime.date,
    end: datetime.date,
    access_token: str = "",
) -> int:
    client = _get_client(access_token)
    res = (
        client.table(TABLE)
        .select("id", count="exact")
        .gte("reading_date", start.isoformat())
        .lte("reading_date", end.isoformat())
        .execute()
    )
    return res.count or 0


# ── 전체 삭제 / 복원 ──────────────────────────────────────────

def clear_all_readings(access_token: str = "") -> str:
    """모든 활성 데이터를 소프트 삭제. 복원에 사용할 배치 ID 반환."""
    client = _get_client(access_token)
    batch_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    client.table(TABLE).update({
        "deleted_at": now,
        "delete_batch_id": batch_id,
    }).is_("deleted_at", "null").execute()
    return batch_id


def get_pending_delete(batch_id: str, access_token: str = "") -> dict | None:
    """12시간 이내 소프트 삭제 배치 정보 반환. 없거나 만료되면 None.
    반환: {batch_id, count, deleted_at, expires_at}"""
    client = _get_client(access_token)
    res = client.rpc("get_pending_delete_meta", {"p_batch_id": batch_id}).execute()
    return res.data


def restore_delete(batch_id: str, access_token: str = "") -> int:
    """소프트 삭제 취소. 복원된 레코드 수 반환."""
    client = _get_client(access_token)
    res = client.rpc("restore_delete_batch", {"p_batch_id": batch_id}).execute()
    return res.data or 0

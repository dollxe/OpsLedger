import base64
import datetime
import json
import os
import sys

import streamlit as st
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ALL_COLUMNS, DONGJU_COLUMNS, SINSEONG_COLUMNS,
    YOLO_MODEL_PATH, EXCEL_MAX_SHEETS,
)
from src.supabase_db import (
    init_db, upsert_reading, get_reading, get_last_reading_before,
    get_readings_in_range, delete_reading, count_readings_in_range,
    clear_all_readings, get_pending_delete, restore_delete,
)
from src.utils import is_holiday, get_weekday_str, get_bosuja, date_to_iso, iso_to_date
from src.interpolation import compute_interpolated_rows, has_negative_diffs
from src.excel_export import export_dongju, export_sinseong
from src.ocr import is_yolo_available, process_meter_image

st.set_page_config(page_title="대기배출시설 운영기록부 관리", layout="wide")


# ──────────────────────────────────────────────
# JWT 유틸
# ──────────────────────────────────────────────
def _token_expiry(access_token: str) -> datetime.datetime:
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.timezone.utc)
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)


def _anon_client():
    from supabase import create_client
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["anon_key"],
    )


# ──────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────
def init_state():
    init_db()
    defaults = {
        "access_token": None,
        "refresh_token": None,
        "user_id": None,
        "user_email": None,
        "delete_batch_id": None,
        "ocr_reader": None,
        "yolo_model": None,
        "interp_seed_offset": 0,
        "interp_rows": None,
        "pending_new_date": None,
        "pending_values": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


@st.cache_resource
def get_ocr_reader():
    from src.ocr import load_ocr_reader
    return load_ocr_reader()


@st.cache_resource
def get_yolo_model():
    from src.ocr import load_yolo_model
    return load_yolo_model()


# ──────────────────────────────────────────────
# 인증
# ──────────────────────────────────────────────
def _try_refresh():
    """액세스 토큰 만료 5분 전이면 갱신."""
    tok = st.session_state.access_token
    if not tok:
        return
    expiry = _token_expiry(tok)
    if expiry - datetime.datetime.now(datetime.timezone.utc) > datetime.timedelta(minutes=5):
        return
    try:
        client = _anon_client()
        resp = client.auth.refresh_session(st.session_state.refresh_token)
        st.session_state.access_token = resp.session.access_token
        st.session_state.refresh_token = resp.session.refresh_token
    except Exception:
        st.session_state.access_token = None


def render_auth():
    st.title("대기배출시설 운영기록부 관리")
    mode = st.radio("", ["로그인", "회원가입"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("이메일")
    password = st.text_input("비밀번호", type="password")

    if mode == "로그인":
        if st.button("로그인", type="primary"):
            try:
                client = _anon_client()
                resp = client.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.access_token = resp.session.access_token
                st.session_state.refresh_token = resp.session.refresh_token
                st.session_state.user_id = resp.user.id
                st.session_state.user_email = resp.user.email
                st.rerun()
            except Exception as e:
                st.error(f"로그인 실패: {e}")
    else:
        st.caption("가입 후 이메일 인증이 필요합니다.")
        if st.button("회원가입", type="primary"):
            try:
                client = _anon_client()
                client.auth.sign_up({"email": email, "password": password})
                st.success("✅ 가입 완료. 이메일을 확인하고 인증 후 로그인하세요.")
            except Exception as e:
                st.error(f"회원가입 실패: {e}")


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────
def col_label(key: str) -> str:
    for k, label in ALL_COLUMNS:
        if k == key:
            return label
    return key


def render_meter_input(col_key: str, label: str) -> float | None:
    """단일 계량기 입력 위젯. 사진 업로드 또는 직접 입력."""
    method = st.radio(
        f"{label} 입력 방식",
        ["직접 입력", "사진 업로드"],
        key=f"method_{col_key}",
        horizontal=True,
        label_visibility="collapsed",
    )

    if method == "직접 입력":
        val = st.number_input(
            label,
            min_value=0.0,
            step=0.1,
            format="%.2f",
            key=f"input_{col_key}",
            label_visibility="collapsed",
        )
        return val if val > 0 else None

    else:  # 사진 업로드
        uploaded = st.file_uploader(
            f"{label} 계량기 사진",
            type=["jpg", "jpeg", "png"],
            key=f"upload_{col_key}",
            label_visibility="collapsed",
        )
        if uploaded is None:
            return None

        with st.spinner("계량기 인식 중..."):
            try:
                ocr_reader = get_ocr_reader()
            except Exception as e:
                import traceback
                st.markdown(f"❌ OCR 모델 로드 실패: {e}")
                st.code(traceback.format_exc())
                return None
            yolo_model = None
            if is_yolo_available():
                try:
                    yolo_model = get_yolo_model()
                except Exception:
                    pass
            result = process_meter_image(uploaded.read(), yolo_model, ocr_reader)

        if result["crop_array"] is not None:
            with st.expander("인식 이미지 보기"):
                st.image(result["crop_array"], channels="BGR", use_column_width=True)

        if result["status"] == "error":
            st.error(result["message"])
            return None

        if result["status"] in ("success", "low_confidence", "ocr_failed"):
            if result["status"] == "low_confidence":
                st.warning(result["message"])
            elif result["status"] == "ocr_failed":
                st.warning(result["message"])

            default_val = result["value"] or 0.0
            corrected = st.number_input(
                f"{label} 인식값 확인/수정",
                value=default_val,
                min_value=0.0,
                step=0.1,
                format="%.2f",
                key=f"corrected_{col_key}",
            )
            return corrected if corrected > 0 else None

    return None


# ──────────────────────────────────────────────
# Tab 1: 데이터 입력
# ──────────────────────────────────────────────
def tab_input(tok: str):
    st.subheader("날짜 선택")
    selected_date = st.date_input(
        "날짜",
        value=datetime.date.today(),
        label_visibility="collapsed",
    )

    if is_holiday(selected_date):
        weekday = get_weekday_str(selected_date)
        st.markdown(
            f"⛔ **선택한 날짜({selected_date} {weekday}요일)는 휴일/공휴일입니다.** 입력할 수 없습니다."
        )
        return

    existing = get_reading(selected_date, access_token=tok)
    if existing:
        st.markdown(f"ℹ️ {selected_date} 데이터가 이미 존재합니다. 덮어쓰기됩니다.")

    st.divider()
    st.subheader("계량기 값 입력")

    col_left, col_right = st.columns(2)
    input_values = {}

    with col_left:
        st.markdown("**🏭 동주**")
        for key, label in DONGJU_COLUMNS:
            st.markdown(f"**{label}**")
            val = render_meter_input(key, label)
            input_values[key] = val

    with col_right:
        st.markdown("**🏭 신성**")
        for key, label in SINSEONG_COLUMNS:
            st.markdown(f"**{label}**")
            val = render_meter_input(key, label)
            input_values[key] = val

    st.divider()

    filled = {k: v for k, v in input_values.items() if v is not None}
    if not filled:
        return

    last = get_last_reading_before(selected_date, access_token=tok)

    GAP_THRESHOLD = 14
    is_initial = last is None
    if last is not None:
        last_date_check = iso_to_date(last["reading_date"])
        if (selected_date - last_date_check).days > GAP_THRESHOLD:
            is_initial = True

    if is_initial and last is not None:
        last_date_check = iso_to_date(last["reading_date"])
        gap_d = (selected_date - last_date_check).days
        st.markdown(f"📋 이전 기록({last_date_check})과 **{gap_d}일** 차이 → 초기 입력으로 처리합니다 (보간 없음).")

    def compute_volume(key, new_val):
        if is_initial or last is None:
            return None
        prev = last.get(f"{key}_power")
        if prev is None or new_val is None:
            return None
        return round(new_val - prev, 2)

    new_row = {"reading_date": selected_date.isoformat()}
    for key, _ in ALL_COLUMNS:
        power_val = input_values.get(key)
        new_row[f"{key}_power"] = power_val
        new_row[f"{key}_volume"] = compute_volume(key, power_val)

    interp_preview = None

    if not is_initial and last is not None:
        last_date = iso_to_date(last["reading_date"])
        gap_days = (selected_date - last_date).days
        if gap_days > 1:
            interp_rows = compute_interpolated_rows(
                last_date=last_date,
                last_values=last,
                new_date=selected_date,
                new_values=new_row,
                seed_offset=st.session_state.interp_seed_offset,
            )
            interp_rows = [r for r in interp_rows if not is_holiday(iso_to_date(r["reading_date"]))]

            neg_warns = has_negative_diffs(interp_rows)
            if neg_warns:
                st.markdown("⚠️ **음수 처리용량 감지:**\n" + "\n".join(neg_warns))

            if interp_rows:
                st.markdown(
                    f"📋 마지막 입력({last_date}, {get_weekday_str(last_date)}요일)과 "
                    f"**{gap_days}일** 차이 → **{len(interp_rows)-1}개** 날짜 자동 생성됩니다."
                )

                preview_data = []
                for r in interp_rows:
                    row_date = iso_to_date(r["reading_date"])
                    row_data = {
                        "날짜": f"{r['reading_date']} ({get_weekday_str(row_date)})",
                        "구분": "보간" if r.get("is_interpolated") else "입력",
                    }
                    for key, label in ALL_COLUMNS:
                        row_data[f"{label} 전력"] = r.get(f"{key}_power")
                        row_data[f"{label} 처리"] = r.get(f"{key}_volume")
                    preview_data.append(row_data)

                st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

                c1, c2 = st.columns([1, 4])
                with c1:
                    if st.button("🔄 재생성"):
                        st.session_state.interp_seed_offset += 1
                        st.rerun()

                interp_preview = interp_rows

    if st.button("✅ 확인 및 저장", type="primary"):
        uid = st.session_state.user_id
        try:
            if interp_preview:
                for r in interp_preview:
                    is_interp = bool(r.get("is_interpolated", 0))
                    upsert_reading(r, is_interpolated=is_interp, access_token=tok, user_id=uid)
            else:
                upsert_reading(new_row, is_interpolated=False, access_token=tok, user_id=uid)
            st.markdown(f"✅ **{selected_date} 데이터가 저장되었습니다.**")
            st.session_state.interp_seed_offset = 0
        except Exception as e:
            st.markdown(f"❌ **저장 실패:** {e}")


# ──────────────────────────────────────────────
# Tab 2: 데이터 조회
# ──────────────────────────────────────────────
def tab_view(tok: str):
    st.subheader("날짜 범위 조회")
    today = datetime.date.today()
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("시작", value=today - datetime.timedelta(days=30), key="view_start")
    with c2:
        end = st.date_input("종료", value=today, key="view_end")

    if start > end:
        st.error("시작 날짜가 종료 날짜보다 늦습니다.")
        return

    readings = get_readings_in_range(start, end, access_token=tok)
    if not readings:
        st.info("해당 기간에 데이터가 없습니다.")
        return

    rows = []
    for r in readings:
        date = iso_to_date(r["reading_date"])
        row = {
            "날짜": r["reading_date"],
            "요일": get_weekday_str(date),
            "구분": "보간" if r.get("is_interpolated") else "입력",
            "보수자(동주)": get_bosuja(date, "dongju"),
            "보수자(신성)": get_bosuja(date, "sinseong"),
        }
        for key, label in ALL_COLUMNS:
            row[f"{label}_전력"] = r.get(f"{key}_power")
            row[f"{label}_처리"] = r.get(f"{key}_volume")
        rows.append(row)

    df = pd.DataFrame(rows)

    def highlight_interp(row):
        if row["구분"] == "보간":
            return ["background-color: #fff8c5"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df.style.apply(highlight_interp, axis=1),
        use_container_width=True,
        height=500,
    )

    st.divider()
    st.subheader("행 삭제")
    del_date_str = st.selectbox(
        "삭제할 날짜",
        options=[r["reading_date"] for r in readings],
        key="del_date",
    )
    if st.button("🗑️ 삭제", type="secondary"):
        if delete_reading(iso_to_date(del_date_str), access_token=tok):
            st.success(f"{del_date_str} 삭제 완료.")
            st.rerun()
        else:
            st.error("삭제 실패.")


# ──────────────────────────────────────────────
# Tab 3: Excel 내보내기
# ──────────────────────────────────────────────
def tab_export(tok: str):
    st.subheader("내보낼 날짜 범위 선택")
    today = datetime.date.today()
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("시작", value=today - datetime.timedelta(days=30), key="exp_start")
    with c2:
        end = st.date_input("종료", value=today, key="exp_end")

    if start > end:
        st.markdown("⛔ 시작 날짜가 종료 날짜보다 늦습니다.")
        return

    readings = get_readings_in_range(start, end, access_token=tok)
    n = len(readings)

    st.markdown(f"📋 선택 기간 내 데이터: **{n}개** 날짜 (시트 {n}개씩 생성)")

    if n == 0:
        st.markdown("내보낼 데이터가 없습니다.")
        return

    if n > EXCEL_MAX_SHEETS:
        st.markdown(
            f"⛔ **시트 수({n})가 Excel 최대({EXCEL_MAX_SHEETS})를 초과합니다.** 범위를 줄여주세요."
        )
        return

    col1, col2 = st.columns(2)

    with col1:
        if st.button("⬇️ 동주_운영일지.xlsx 생성", type="primary"):
            with st.spinner("동주 엑셀 생성 중..."):
                try:
                    buf = export_dongju(readings)
                    st.download_button(
                        label="동주_운영일지.xlsx 다운로드",
                        file_name=f"동주_운영일지_{start}_{end}.xlsx",
                        data=buf,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.markdown(f"❌ **생성 실패:** {e}")

    with col2:
        if st.button("⬇️ 신성_운영일지.xlsx 생성", type="primary"):
            with st.spinner("신성 엑셀 생성 중..."):
                try:
                    buf = export_sinseong(readings)
                    st.download_button(
                        label="신성_운영일지.xlsx 다운로드",
                        data=buf,
                        file_name=f"신성_운영일지_{start}_{end}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.markdown(f"❌ **생성 실패:** {e}")


# ──────────────────────────────────────────────
# Tab 4: 설정
# ──────────────────────────────────────────────
def tab_settings(tok: str):
    st.subheader("데이터 초기화")

    batch_id = st.session_state.delete_batch_id
    meta = get_pending_delete(batch_id, access_token=tok) if batch_id else None

    if meta:
        # 복원 가능 상태 — 삭제 취소 버튼만 표시
        try:
            expires_str = meta.get("expires_at", "")
            if expires_str.endswith("Z"):
                expires_str = expires_str[:-1] + "+00:00"
            expires = datetime.datetime.fromisoformat(expires_str)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            remaining = expires - datetime.datetime.now(datetime.timezone.utc)
            hours = max(0, int(remaining.total_seconds() // 3600))
            mins = max(0, int((remaining.total_seconds() % 3600) // 60))
            time_str = f"{hours}시간 {mins}분"
        except Exception:
            time_str = "알 수 없음"

        st.warning(
            f"⚠️ **{meta['count']}개** 데이터가 삭제 예정입니다.  \n"
            f"복원 가능 시간: **{time_str}** 남음"
        )
        if st.button("↩️ 삭제 취소 (복원)", type="primary"):
            restored = restore_delete(batch_id, access_token=tok)
            st.session_state.delete_batch_id = None
            st.success(f"✅ {restored}개 데이터가 복원되었습니다.")
            st.rerun()
        return

    # 만료된 배치 ID 정리
    if batch_id:
        st.session_state.delete_batch_id = None

    # 삭제 UI
    st.markdown("모든 데이터를 일괄 삭제합니다. **12시간 이내에 취소 버튼으로 복원**할 수 있습니다.")
    confirm = st.text_input("확인을 위해 `전체삭제` 를 입력하세요", key="confirm_clear")
    if st.button("🗑️ 전체 데이터 삭제", type="secondary", disabled=(confirm != "전체삭제")):
        try:
            new_batch_id = clear_all_readings(access_token=tok)
            st.session_state.delete_batch_id = new_batch_id
            st.success("✅ 전체 데이터가 삭제되었습니다. 12시간 이내 복원 가능합니다.")
            st.rerun()
        except Exception as e:
            st.error(f"삭제 실패: {e}")

    st.divider()
    st.subheader("계정")
    st.write(f"로그인 이메일: `{st.session_state.user_email}`")
    if st.button("로그아웃"):
        for key in ["access_token", "refresh_token", "user_id", "user_email", "delete_batch_id"]:
            st.session_state[key] = None
        st.rerun()


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    init_state()
    st.title("대기배출시설 운영기록부 관리")

    if not st.session_state.access_token:
        render_auth()
        return

    _try_refresh()

    if not st.session_state.access_token:
        st.warning("세션이 만료되었습니다. 다시 로그인하세요.")
        render_auth()
        return

    tok = st.session_state.access_token

    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 데이터 입력", "📊 데이터 조회", "📤 Excel 내보내기", "⚙️ 설정",
    ])
    with tab1:
        tab_input(tok)
    with tab2:
        tab_view(tok)
    with tab3:
        tab_export(tok)
    with tab4:
        tab_settings(tok)


if __name__ == "__main__":
    main()

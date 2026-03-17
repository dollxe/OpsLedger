import datetime
import os
import sys

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ALL_COLUMNS, DONGJU_COLUMNS, SINSEONG_COLUMNS, EXCEL_MAX_SHEETS
from src.database import (
    init_db, upsert_reading, get_reading, get_last_reading_before,
    get_readings_in_range, delete_reading,
)
from src.utils import is_holiday, get_weekday_str, get_bosuja, iso_to_date
from src.interpolation import compute_interpolated_rows, has_negative_diffs
from src.excel_export import export_dongju, export_sinseong

st.set_page_config(page_title="대기운영일지 관리", layout="wide")


def init_state():
    init_db()
    if "interp_seed_offset" not in st.session_state:
        st.session_state.interp_seed_offset = 0


# ──────────────────────────────────────────────
# Tab 1: 데이터 입력
# ──────────────────────────────────────────────
def tab_input():
    st.subheader("날짜 선택")
    selected_date = st.date_input("날짜", value=datetime.date.today(), label_visibility="collapsed")

    if is_holiday(selected_date):
        weekday = get_weekday_str(selected_date)
        st.markdown(f"⛔ **{selected_date} ({weekday}요일)은 휴일입니다.** 입력할 수 없습니다.")
        return

    existing = get_reading(selected_date)
    if existing:
        st.markdown(f"ℹ️ {selected_date} 데이터가 이미 존재합니다. 덮어쓰기됩니다.")

    st.divider()
    st.subheader("계량기 값 입력")

    col_left, col_right = st.columns(2)
    input_values = {}

    with col_left:
        st.markdown("**🏭 동주**")
        for key, label in DONGJU_COLUMNS:
            val = st.number_input(label, min_value=0.0, step=0.1, format="%.2f", key=f"inp_{key}")
            input_values[key] = val if val > 0 else None

    with col_right:
        st.markdown("**🏭 신성**")
        for key, label in SINSEONG_COLUMNS:
            val = st.number_input(label, min_value=0.0, step=0.1, format="%.2f", key=f"inp_{key}")
            input_values[key] = val if val > 0 else None

    st.divider()

    filled = {k: v for k, v in input_values.items() if v is not None}
    if not filled:
        return

    last = get_last_reading_before(selected_date)

    GAP_THRESHOLD = 14
    is_initial = last is None
    if last is not None:
        last_date_check = iso_to_date(last["reading_date"])
        if (selected_date - last_date_check).days > GAP_THRESHOLD:
            is_initial = True

    if is_initial and last is not None:
        last_date_check = iso_to_date(last["reading_date"])
        gap_d = (selected_date - last_date_check).days
        st.markdown(f"📋 이전 기록({last_date_check})과 **{gap_d}일** 차이 → 초기 입력으로 처리됩니다 (보간 없음).")

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

                c1, _ = st.columns([1, 4])
                with c1:
                    if st.button("🔄 재생성"):
                        st.session_state.interp_seed_offset += 1
                        st.rerun()

                interp_preview = interp_rows

    if st.button("✅ 확인 및 저장", type="primary"):
        try:
            if interp_preview:
                for r in interp_preview:
                    upsert_reading(r, is_interpolated=bool(r.get("is_interpolated", 0)))
            else:
                upsert_reading(new_row, is_interpolated=False)
            st.success(f"✅ {selected_date} 데이터가 저장되었습니다.")
            st.session_state.interp_seed_offset = 0
        except Exception as e:
            st.error(f"저장 실패: {e}")


# ──────────────────────────────────────────────
# Tab 2: 데이터 조회
# ──────────────────────────────────────────────
def tab_view():
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

    readings = get_readings_in_range(start, end)
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

    st.dataframe(df.style.apply(highlight_interp, axis=1), use_container_width=True, height=500)

    st.divider()
    st.subheader("행 삭제")
    del_date_str = st.selectbox(
        "삭제할 날짜", options=[r["reading_date"] for r in readings], key="del_date"
    )
    if st.button("🗑️ 삭제", type="secondary"):
        if delete_reading(iso_to_date(del_date_str)):
            st.success(f"{del_date_str} 삭제 완료.")
            st.rerun()
        else:
            st.error("삭제 실패.")


# ──────────────────────────────────────────────
# Tab 3: Excel 내보내기
# ──────────────────────────────────────────────
def tab_export():
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

    readings = get_readings_in_range(start, end)
    n = len(readings)
    st.markdown(f"📋 선택 기간 내 데이터: **{n}개** 날짜 (시트 {n}개씩 생성)")

    if n == 0:
        st.markdown("내보낼 데이터가 없습니다.")
        return

    if n > EXCEL_MAX_SHEETS:
        st.markdown(f"⛔ 시트 수({n})가 최대({EXCEL_MAX_SHEETS})를 초과합니다. 범위를 줄여주세요.")
        return

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬇️ 동주_운영일지.xlsx 생성", type="primary"):
            with st.spinner("생성 중..."):
                try:
                    buf = export_dongju(readings)
                    st.download_button(
                        "동주_운영일지.xlsx 다운로드", data=buf,
                        file_name=f"동주_운영일지_{start}_{end}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.error(f"생성 실패: {e}")

    with col2:
        if st.button("⬇️ 신성_운영일지.xlsx 생성", type="primary"):
            with st.spinner("생성 중..."):
                try:
                    buf = export_sinseong(readings)
                    st.download_button(
                        "신성_운영일지.xlsx 다운로드", data=buf,
                        file_name=f"신성_운영일지_{start}_{end}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.error(f"생성 실패: {e}")


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    init_state()
    st.title("대기배출시설 운영기록부 관리")
    tab1, tab2, tab3 = st.tabs(["📝 데이터 입력", "📊 데이터 조회", "📤 Excel 내보내기"])
    with tab1:
        tab_input()
    with tab2:
        tab_view()
    with tab3:
        tab_export()


if __name__ == "__main__":
    main()

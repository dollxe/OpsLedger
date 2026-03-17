import datetime
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALL_COLUMNS
from src.utils import get_business_days_between

POWER_KEYS = [f"{key}_power" for key, _ in ALL_COLUMNS]


def compute_interpolated_rows(
    last_date: datetime.date,
    last_values: dict,
    new_date: datetime.date,
    new_values: dict,
    seed_offset: int = 0,
) -> list[dict]:
    """
    last_date(미포함) ~ new_date(포함) 사이 영업일에 대해
    각 컬럼의 누적값을 자연스럽게 분배한 행 목록을 반환.

    반환값: [{'reading_date': 'YYYY-MM-DD', 'col_power': float, 'col_volume': float, ...}, ...]
    - 중간 날짜: is_interpolated=True
    - new_date: is_interpolated=False
    """
    biz_days = get_business_days_between(last_date, new_date)
    if not biz_days:
        return []

    n_days = len(biz_days)
    base_seed = (
        int(last_date.strftime("%Y%m%d")) + int(new_date.strftime("%Y%m%d")) + seed_offset
    )
    rng = random.Random(base_seed)

    # 컬럼별로 daily diff 배열 계산
    daily_diffs: dict[str, list[float]] = {}
    for key in POWER_KEYS:
        last_val = last_values.get(key)
        new_val = new_values.get(key)
        if last_val is None or new_val is None:
            daily_diffs[key] = [None] * n_days
            continue
        total = new_val - last_val
        diffs = _distribute(total, n_days, rng)
        daily_diffs[key] = diffs

    # 날짜별 행 생성
    rows = []
    cumulative = {key: last_values.get(key) for key in POWER_KEYS}
    for i, date in enumerate(biz_days):
        row = {"reading_date": date.isoformat()}
        is_last = date == new_date
        row["is_interpolated"] = 0 if is_last else 1
        for key in POWER_KEYS:
            diff = daily_diffs[key][i]
            prev = cumulative[key]
            if diff is None or prev is None:
                power_val = new_values.get(key) if is_last else None
                vol_val = None
            else:
                power_val = round(prev + diff, 2)
                vol_val = round(diff, 2)
            cumulative[key] = power_val
            vol_key = key.replace("_power", "_volume")
            row[key] = power_val
            row[vol_key] = vol_val
        rows.append(row)

    # 마지막 날짜(new_date)의 누적값을 정확히 맞춤
    if rows and biz_days[-1] == new_date:
        last_row = rows[-1]
        for key in POWER_KEYS:
            target = new_values.get(key)
            if target is not None:
                prev_power = rows[-2][key] if len(rows) > 1 else last_values.get(key)
                last_row[key] = target
                vol_key = key.replace("_power", "_volume")
                last_row[vol_key] = round(target - (prev_power or target), 2)

    return rows


def _distribute(total: float, n: int, rng: random.Random) -> list[float]:
    """total을 n개로 분배. 정수 부분은 균등 배분, 소수 부분은 첫 칸에 배분 후 shuffle."""
    if n == 1:
        return [round(total, 2)]

    base = total / n
    # 각 구간에 base ± 약간의 편차 부여
    parts = [base] * n

    # 소량의 랜덤 노이즈 추가 (총합 보정)
    noise_range = abs(base) * 0.15 if base != 0 else 0.1
    adjustments = [rng.uniform(-noise_range, noise_range) for _ in range(n)]
    adj_sum = sum(adjustments)
    # 마지막 구간에서 오차 흡수
    adjustments[-1] -= adj_sum

    parts = [round(p + a, 2) for p, a in zip(parts, adjustments)]
    # 총합 정확하게 맞추기
    diff = round(total - sum(parts), 2)
    parts[-1] = round(parts[-1] + diff, 2)

    rng.shuffle(parts)
    return parts


def has_negative_diffs(rows: list[dict]) -> list[str]:
    """음수 처리용량 감지 → 경고 메시지 목록 반환"""
    warnings = []
    for row in rows:
        date = row.get("reading_date", "?")
        for key, label in ALL_COLUMNS:
            vol = row.get(f"{key}_volume")
            if vol is not None and vol < 0:
                warnings.append(f"{date}: {label} 처리용량 음수({vol})")
    return warnings

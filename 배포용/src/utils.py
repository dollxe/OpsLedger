import datetime
import holidays

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import KOREAN_WEEKDAYS, DONGJU_BOSUJA_NAME, SINSEONG_BOSUJA_NAME

_kr_holidays = None

def get_kr_holidays(year: int):
    global _kr_holidays
    if _kr_holidays is None or year not in _kr_holidays:
        _kr_holidays = holidays.KR(years=range(year - 1, year + 2))
    return _kr_holidays


def is_holiday(date: datetime.date) -> bool:
    """토/일요일 또는 한국 공휴일이면 True"""
    if date.weekday() >= 5:  # 5=토, 6=일
        return True
    return date in get_kr_holidays(date.year)


def get_weekday_str(date: datetime.date) -> str:
    return KOREAN_WEEKDAYS[date.weekday()]


def get_bosuja(date: datetime.date, facility: str = "dongju") -> str:
    """월/수/금이면 보수자 이름, 그 외 공백"""
    if date.weekday() in (0, 2, 4):  # 0=월, 2=수, 4=금
        return DONGJU_BOSUJA_NAME if facility == "dongju" else SINSEONG_BOSUJA_NAME
    return ""


def date_to_iso(date: datetime.date) -> str:
    return date.isoformat()


def iso_to_date(iso_str: str) -> datetime.date:
    return datetime.date.fromisoformat(iso_str)


def get_business_days_between(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """start 초과 ~ end 포함 사이의 영업일(비휴일) 목록"""
    result = []
    current = start + datetime.timedelta(days=1)
    while current <= end:
        if not is_holiday(current):
            result.append(current)
        current += datetime.timedelta(days=1)
    return result


def format_sheet_name(date: datetime.date, include_year: bool = False) -> str:
    """시트명: M월D일, 연도 필요시 YYYY_M월D일"""
    if include_year:
        return f"{date.year}_{date.month}월{date.day}일"
    return f"{date.month}월{date.day}일"

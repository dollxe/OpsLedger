import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_PATH = os.path.join(BASE_DIR, "data", "8.대기운영일지(4종) 엑셀.xlsx")
DB_PATH = os.path.join(BASE_DIR, "db", "meter_readings.db")
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "models", "meter_yolo.pt")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")

EXCEL_MAX_SHEETS = 1024

KOREAN_WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']

# 컬럼 정의: (DB 컬럼 prefix, 표시명)
DONGJU_COLUMNS = [
    ("dong_bunche", "동주 분체"),
    ("dong_aekche", "동주 액체"),
    ("dong_pimak",  "동주 피막"),
]
SINSEONG_COLUMNS = [
    ("sin_aekche", "신성 액체"),
    ("sin_yeonma", "신성 연마"),
    ("sin_syote",  "신성 쇼트"),
]
ALL_COLUMNS = DONGJU_COLUMNS + SINSEONG_COLUMNS

# 엑셀 셀 맵핑 (동주(보수o) 시트)
DONGJU_SHEET = "동주(보수o)"
DONGJU_CELL_MAP = {
    "dong_bunche": {"power": "H19", "volume": "J19"},
    "dong_aekche": {"power": "H23", "volume": "J23"},
    "dong_pimak":  {"power": "H25", "volume": "J25"},
}
DONGJU_BOSUJA_CELL = "O30"
DONGJU_BOSUJA_NAME = "아구스"  # 월/수/금

# 엑셀 셀 맵핑 (신성(보수o) 시트)
SINSEONG_SHEET = "신성(보수o)"
SINSEONG_CELL_MAP = {
    "sin_aekche": {"power": "H19", "volume": "J19"},
    "sin_yeonma": {"power": "H23", "volume": "J23"},
    "sin_syote":  {"power": "H25", "volume": "J25"},
}
SINSEONG_BOSUJA_CELL = "O30"
SINSEONG_BOSUJA_NAME = "김봉희"  # 월/수/금

DATE_CELL = "B6"

# 보간 시 사용할 최대 seed 오프셋
INTERP_SEED_MAX = 9999

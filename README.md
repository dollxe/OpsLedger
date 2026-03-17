# OpsLedger — 대기배출시설 운영기록부 관리

대기배출시설의 계량기 수치를 입력·보관하고, 법정 서식 Excel 파일로 내보내는 웹 애플리케이션입니다.

---

## 주요 기능

- **계량기 값 입력** — 동주(분체·액체·피막) / 신성(액체·연마·쇼트) 6개 계량기
- **자동 보간** — 마지막 입력일과 오늘 사이 공백 날짜를 자연스러운 분포로 자동 채움
- **휴일 자동 제외** — 토·일·한국 공휴일은 입력 및 보간에서 제외
- **Excel 내보내기** — 법정 서식 템플릿 기반, 날짜별 시트 자동 생성
- **전체 데이터 삭제 / 복원** — 12시간 이내 실수 취소 가능

---

## 배포 방식

### A. Streamlit Cloud + Supabase (권장 — 브라우저 URL 접속)

사용자는 URL만 열면 됨. 데이터는 Supabase(PostgreSQL)에 사용자별로 격리 저장.

**Supabase 설정**
1. [supabase.com](https://supabase.com) 에서 프로젝트 생성
2. SQL 에디터에서 `supabase_schema.sql` 실행
3. Project Settings → API 에서 URL, anon key 복사

**Streamlit Cloud 배포**
1. [share.streamlit.io](https://share.streamlit.io) 에서 이 저장소 연결
2. Main file: `app.py`
3. Settings → Secrets 에 아래 내용 입력:

```toml
[supabase]
url = "https://your-project-id.supabase.co"
anon_key = "eyJ..."
```

---

### B. 포터블 버전 (인터넷 없이 로컬 실행)

Python 설치 없이 Windows PC에서 실행. 데이터는 로컬 SQLite에 저장.

`배포용/` 폴더를 압축해서 전달 → 받는 사람이 아래 순서대로 실행:

1. `바탕화면에_추가.bat` 실행 → 바탕화면 아이콘 생성
2. 아이콘 더블클릭 → 최초 1회 자동 설치 (Python + 라이브러리, 약 5~10분)
3. 이후 아이콘 더블클릭만 하면 브라우저 자동 오픈

---

## 로컬 개발 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 프로젝트 구조

```
├── app.py                  # 메인 앱 (Supabase 버전)
├── app_local.py            # 로컬 앱 (SQLite, OCR 없음)
├── config.py               # 컬럼 정의, 셀 매핑, 경로 설정
├── src/
│   ├── database.py         # SQLite CRUD
│   ├── supabase_db.py      # Supabase CRUD + 소프트 삭제
│   ├── interpolation.py    # 날짜 공백 자동 보간
│   ├── excel_export.py     # Excel 템플릿 기반 내보내기
│   ├── ocr.py              # 계량기 이미지 인식 (YOLOv8 + EasyOCR)
│   └── utils.py            # 날짜, 휴일, 보수자 유틸
├── data/
│   └── 8.대기운영일지(4종) 엑셀.xlsx   # Excel 서식 템플릿
├── supabase_schema.sql     # Supabase 테이블·RLS·RPC 스키마
├── 배포용/                  # 포터블 배포 패키지
└── requirements.txt
```

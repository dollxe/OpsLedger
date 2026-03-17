# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Korean-language Streamlit web application for managing air emission facility operation logs (대기배출시설 운영기록부). Tracks meter readings for two facilities (동주, 신성), handles OCR-based meter image recognition, interpolates missing data, and generates formatted Excel reports.

## Running the App

```bash
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
```

## Installing Dependencies

```bash
pip install -r requirements.txt
```

The `packages/` directory isolates certain dependencies to resolve Windows DLL issues with PyTorch/CUDA.

## Architecture

### Entry Point
`app.py` — Single-file Streamlit app with three tabs:
1. **데이터 입력**: Date selection + meter reading input (direct or OCR from image)
2. **데이터 조회**: Date-range queries, interpolated row highlighting, record deletion
3. **Excel 내보내기**: Generate downloadable Excel reports per facility

### Core Modules (`src/`)
- `database.py` — SQLite CRUD via `db/meter_readings.db`; WAL mode; unique constraint on `reading_date`
- `ocr.py` — YOLOv8 meter region detection (`models/meter_yolo.pt`) → EasyOCR digit recognition
- `interpolation.py` — Fills gaps >14 days with deterministic randomized daily distributions (seeded by date pair)
- `excel_export.py` — Copies Excel template (`data/8.대기운영일지(4종) 엑셀.xlsx`) and populates predefined cell positions
- `utils.py` — Date conversion, Korean holiday checks, facility mappings

### Configuration (`config.py`)
Central source of truth for:
- **Column names** per facility (동주: 분체/액체/피막; 신성: 액체/연마/쇼트)
- **Excel cell mappings** for each template sheet ("동주(보수o)", "신성(보수o)")
- **Maintenance person schedule** (Mon/Wed/Fri assignments)
- File paths: `DB_PATH`, `YOLO_MODEL_PATH`

### Data Flow
```
User input / OCR image
  → Validation (holiday/weekend check)
  → Interpolation (if date gap detected)
  → SQLite upsert
  → Excel template copy → cell mapping → BytesIO download
```

### Key Design Decisions
- Streamlit `@st.cache_resource` caches OCR/YOLO model loads across reruns
- Interpolation uses `random.Random` with a deterministic seed so the same date pair always produces the same fill values
- Excel output uses `openpyxl copy_worksheet()` to preserve all template formatting/print settings
- All UI text and variable names are in Korean to match the operational context

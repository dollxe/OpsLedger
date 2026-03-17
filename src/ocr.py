"""
계량기 사진에서 숫자를 읽어내는 모듈.
YOLOv8으로 계량기 영역 탐지 → EasyOCR로 숫자 인식.
YOLO 모델 없을 시 EasyOCR 직접 적용 (fallback).
"""
import os
import sys
import re
from typing import Optional
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib

# 프로젝트 로컬 packages/ 디렉토리 추가 (subprocess 환경 격리 우회)
_local_pkgs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages")
if _local_pkgs not in sys.path:
    sys.path.insert(1, _local_pkgs)
importlib.invalidate_caches()

# torch DLL 의존성 경로 추가 (Windows: --target 설치 시 DLL 탐색 경로 미설정 문제 해결)
_torch_lib = os.path.join(_local_pkgs, "torch", "lib")
if os.path.isdir(_torch_lib):
    try:
        os.add_dll_directory(_torch_lib)
    except Exception:
        pass

from config import YOLO_MODEL_PATH

OCR_CONFIDENCE_THRESHOLD = 0.7


def is_yolo_available() -> bool:
    return os.path.exists(YOLO_MODEL_PATH)


def load_yolo_model():
    """YOLOv8 모델 로드. 캐싱은 호출부(Streamlit session_state)에서 처리."""
    from ultralytics import YOLO
    return YOLO(YOLO_MODEL_PATH)


def load_ocr_reader():
    """EasyOCR 리더 로드 (영문 숫자 전용). 캐싱은 호출부에서 처리."""
    import easyocr
    return easyocr.Reader(['en'], gpu=False)


def detect_meter_region(
    image_array: np.ndarray,
    yolo_model,
    conf_threshold: float = 0.5,
) -> tuple[Optional[np.ndarray], Optional[list]]:
    """
    YOLO로 계량기 영역 탐지.
    Returns: (cropped_image, bbox) or (None, None) if no detection.
    """
    results = yolo_model(image_array, conf=conf_threshold, verbose=False)
    if not results or len(results[0].boxes) == 0:
        return None, None

    # 가장 confidence 높은 박스 선택
    boxes = results[0].boxes
    best_idx = int(boxes.conf.argmax())
    x1, y1, x2, y2 = boxes.xyxy[best_idx].tolist()
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

    cropped = image_array[y1:y2, x1:x2]
    bbox = [x1, y1, x2, y2]
    return cropped, bbox


def read_digits_from_image(
    image_array: np.ndarray,
    ocr_reader,
) -> tuple[Optional[float], float]:
    """
    EasyOCR로 이미지에서 숫자 읽기.
    Returns: (value, confidence) - value=None if failed.
    """
    results = ocr_reader.readtext(
        image_array,
        allowlist='0123456789.',
        detail=1,
    )
    if not results:
        return None, 0.0

    # confidence 높은 순 정렬
    results_sorted = sorted(results, key=lambda r: r[2], reverse=True)

    # 숫자로 파싱 가능한 첫 번째 결과 사용
    for _, text, conf in results_sorted:
        cleaned = re.sub(r'[^0-9.]', '', text)
        if not cleaned:
            continue
        # 소수점 중복 제거
        parts = cleaned.split('.')
        if len(parts) > 2:
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        try:
            value = float(cleaned)
            return value, conf
        except ValueError:
            continue

    return None, 0.0


def process_meter_image(
    image_bytes: bytes,
    yolo_model=None,
    ocr_reader=None,
) -> dict:
    """
    전체 파이프라인: 이미지 bytes → 숫자값.
    Returns: {
        'value': float or None,
        'confidence': float,
        'status': 'success' | 'no_detection' | 'ocr_failed' | 'low_confidence' | 'error',
        'message': str,
        'crop_array': np.ndarray or None,
        'bbox': list or None,
    }
    """
    try:
        import cv2
        img_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            return _fail("error", "이미지를 읽을 수 없습니다.")

        # YOLO로 계량기 영역 탐지 (모델 있을 때만)
        crop = image
        bbox = None
        if yolo_model is not None and is_yolo_available():
            crop, bbox = detect_meter_region(image, yolo_model)
            if crop is None:
                # YOLO 탐지 실패 → 전체 이미지로 OCR 시도
                crop = image
                bbox = None

        # EasyOCR로 숫자 읽기
        if ocr_reader is None:
            return _fail("error", "OCR 모델이 로드되지 않았습니다.")

        value, conf = read_digits_from_image(crop, ocr_reader)

        if value is None:
            return _fail("ocr_failed", "숫자를 인식하지 못했습니다. 직접 입력해주세요.", crop, bbox)

        if conf < OCR_CONFIDENCE_THRESHOLD:
            return {
                "value": value,
                "confidence": conf,
                "status": "low_confidence",
                "message": f"인식 신뢰도가 낮습니다({conf:.0%}). 값을 확인해주세요.",
                "crop_array": crop,
                "bbox": bbox,
            }

        return {
            "value": value,
            "confidence": conf,
            "status": "success",
            "message": f"인식 완료 (신뢰도: {conf:.0%})",
            "crop_array": crop,
            "bbox": bbox,
        }

    except Exception as e:
        return _fail("error", f"처리 중 오류: {str(e)}")


def _fail(status: str, message: str, crop=None, bbox=None) -> dict:
    return {
        "value": None,
        "confidence": 0.0,
        "status": status,
        "message": message,
        "crop_array": crop,
        "bbox": bbox,
    }

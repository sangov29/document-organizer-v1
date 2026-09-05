from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import cv2
import fitz
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from pytesseract import Output

from app.core.config import settings


@dataclass(frozen=True)
class PreprocessedPage:
    png: bytes
    orientation_degrees: int | None
    orientation_confidence: float | None
    skew_degrees: float
    quality_status: str
    quality_metadata: dict
    needs_review: bool
    noise_reduction_applied: bool


def decode_page(data: bytes, mime_type: str) -> Image.Image:
    if mime_type == "application/pdf":
        document = fitz.open(stream=data, filetype="pdf")
        if document.page_count != 1:
            raise ValueError("preprocessing expects a single-page PDF artifact")
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
    return ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")


def detect_orientation(image: Image.Image) -> tuple[int | None, float | None]:
    try:
        result = pytesseract.image_to_osd(image, output_type=Output.DICT)
        return int(result["rotate"]), float(result["orientation_conf"])
    except (pytesseract.TesseractError, KeyError, ValueError):
        return None, None


def detect_skew(gray: np.ndarray) -> float:
    _, foreground = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    points = np.column_stack(np.where(foreground > 0))
    if len(points) < 100:
        return 0.0
    angle = float(cv2.minAreaRect(points.astype(np.float32))[-1])
    # OpenCV 4.11 reports [0, 90]. Convert it to the signed correction angle
    # expected by rotate_bound: upright=0, CCW page tilt=>clockwise correction.
    return 90.0 - angle if angle > 45.0 else -angle


def rotate_bound(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cosine, sine = abs(matrix[0, 0]), abs(matrix[0, 1])
    out_width = int(height * sine + width * cosine)
    out_height = int(height * cosine + width * sine)
    matrix[0, 2] += out_width / 2 - center[0]
    matrix[1, 2] += out_height / 2 - center[1]
    return cv2.warpAffine(image, matrix, (out_width, out_height), borderValue=(255, 255, 255))


def preprocess_page(data: bytes, mime_type: str) -> PreprocessedPage:
    image = decode_page(data, mime_type)
    orientation, orientation_confidence = detect_orientation(image)
    orientation_uncertain = orientation is None or (orientation_confidence or 0) < settings.pp_orientation_confidence
    if not orientation_uncertain and orientation:
        image = image.rotate(-orientation, expand=True, fillcolor="white")

    array = np.array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast_score = float(gray.std())
    width, height = image.size
    resolution_low = width < settings.pp_min_width or height < settings.pp_min_height
    blur_low = blur_score < settings.pp_blur_threshold
    contrast_low = contrast_score < settings.pp_contrast_threshold

    skew = detect_skew(gray)
    skew_supported = abs(skew) <= settings.pp_deskew_max_degrees
    if abs(skew) >= 0.25 and skew_supported:
        array = rotate_bound(array, skew)

    noise_applied = False
    if settings.pp_noise_reduction_enabled:
        array = cv2.fastNlMeansDenoisingColored(array, None, 5, 5, 7, 21)
        noise_applied = True

    needs_review = orientation_uncertain or resolution_low or blur_low or contrast_low or not skew_supported
    metadata = {
        "width": width,
        "height": height,
        "blur_score": round(blur_score, 4),
        "contrast_score": round(contrast_score, 4),
        "resolution_low": resolution_low,
        "blur_low": blur_low,
        "contrast_low": contrast_low,
        "orientation_uncertain": orientation_uncertain,
        "skew_supported": skew_supported,
        "thresholds": {
            "min_width": settings.pp_min_width,
            "min_height": settings.pp_min_height,
            "blur": settings.pp_blur_threshold,
            "contrast": settings.pp_contrast_threshold,
            "orientation_confidence": settings.pp_orientation_confidence,
            "deskew_max_degrees": settings.pp_deskew_max_degrees,
        },
    }
    output = BytesIO()
    Image.fromarray(array).save(output, "PNG", optimize=True)
    return PreprocessedPage(
        png=output.getvalue(), orientation_degrees=orientation,
        orientation_confidence=orientation_confidence, skew_degrees=skew,
        quality_status="low_quality" if needs_review else "usable",
        quality_metadata=metadata, needs_review=needs_review,
        noise_reduction_applied=noise_applied,
    )

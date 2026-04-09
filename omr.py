from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

import cv2
import numpy as np


@dataclass
class GradeResult:
    total_questions: int
    correct_count: int
    score_percent: float
    detected_answers: list[str]
    answer_key: list[str]
    details: list[dict[str, str]]
    method: str
    warnings: list[str]


SUPPORTED_OPTIONS = [chr(ord("A") + i) for i in range(8)]


def _normalize_answer_token(token: str, valid_options: list[str]) -> set[str]:
    separators = ["+", "|", "/", "&", " "]
    normalized = token.upper().strip()
    for sep in separators:
        normalized = normalized.replace(sep, ",")

    if "," in normalized:
        parts = [x.strip() for x in normalized.split(",") if x.strip()]
    else:
        # allow forms like "AC" for multi-choice
        parts = list(normalized)

    picked = {x for x in parts if x in valid_options}
    if not picked or len(picked) != len(parts):
        raise ValueError(f"答案 '{token}' 无效，可选范围：{','.join(valid_options)}")
    return picked


def parse_answer_key(text: str, num_questions: int, options: int) -> list[set[str]]:
    """Parse answer key. Supports single choice (A) and multi-choice (A+C/A|C/AC)."""
    if not text.strip():
        raise ValueError("请输入正确答案，例如：A,B,C,D 或 A+C,B,AC,D")

    normalized = text.replace("，", ",").replace("\n", ",").replace(";", ",")
    tokens = [x.strip() for x in normalized.split(",") if x.strip()]

    if len(tokens) != num_questions:
        raise ValueError(f"答案数量与题目数量不一致：需要 {num_questions} 个，实际 {len(tokens)} 个。")

    valid_options = SUPPORTED_OPTIONS[:options]
    result: list[set[str]] = []
    for idx, token in enumerate(tokens, start=1):
        try:
            result.append(_normalize_answer_token(token, valid_options))
        except ValueError as exc:
            raise ValueError(f"第 {idx} 题{exc}") from exc

    return result


def _format_answer(answer: set[str]) -> str:
    if not answer:
        return "未识别"
    return ",".join(sorted(answer))


def _sort_points(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2)
    rect = np.zeros((4, 2), dtype="float32")

    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]

    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _warp_paper(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edge = cv2.Canny(blur, 50, 150)

    contours, _ = cv2.findContours(edge, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    paper = None
    image_area = image.shape[0] * image.shape[1]
    for contour in contours[:15]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.2:
            continue

        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            paper = approx
            break

    if paper is None:
        return image

    rect = _sort_points(paper)
    (tl, tr, br, bl) = rect

    max_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if max_w <= 0 or max_h <= 0:
        return image

    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype="float32"
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_w, max_h))


def _binarize(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]


def _detect_options_in_cell(
    binary: np.ndarray,
    y1: int,
    y2: int,
    x1: int,
    x2: int,
    options: int,
    allow_multiple: bool,
) -> set[str]:
    cell = binary[y1:y2, x1:x2]
    if cell.size == 0:
        return set()

    # remove question number area and margins
    h, w = cell.shape
    top = int(h * 0.22)
    left = int(w * 0.08)
    right = int(w * 0.92)
    answer_area = cell[top:h, left:right]
    if answer_area.size == 0:
        return set()

    ah, aw = answer_area.shape
    option_h = ah // options
    if option_h <= 0:
        return set()

    rates: list[float] = []
    for i in range(options):
        oy1 = i * option_h
        oy2 = (i + 1) * option_h if i < options - 1 else ah
        roi = answer_area[oy1:oy2, 0:aw]
        if roi.size == 0:
            rates.append(0.0)
            continue
        rates.append(cv2.countNonZero(roi) / float(roi.size))

    top_rate = max(rates)
    if top_rate < 0.07:
        return set()

    avg = float(np.mean(rates))
    threshold = max(0.08, avg + 0.02, top_rate * 0.6)
    selected_idx = [i for i, rate in enumerate(rates) if rate >= threshold]

    if not selected_idx:
        selected_idx = [int(np.argmax(rates))]

    if not allow_multiple and len(selected_idx) > 1:
        selected_idx = [int(np.argmax(rates))]

    return {chr(ord("A") + idx) for idx in selected_idx}


def grade_answer_sheet(
    image_path: str,
    answer_key: list[set[str]],
    options: int = 4,
    questions_per_row: int = 20,
    allow_multiple: bool = True,
) -> dict[str, Any]:
    if not answer_key:
        raise ValueError("答案不能为空。")
    if questions_per_row <= 0:
        raise ValueError("每行题数必须大于 0。")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("无法读取图片，请确认上传的是有效图像文件。")

    warped = _warp_paper(image)
    binary = _binarize(warped)

    total_questions = len(answer_key)
    row_count = ceil(total_questions / questions_per_row)
    h, w = binary.shape

    row_h = h // row_count
    col_w = w // questions_per_row
    if row_h <= 0 or col_w <= 0:
        raise ValueError("参数与答题卡尺寸不匹配，请检查题量或每行题数设置。")

    detected_sets: list[set[str]] = []
    for q in range(total_questions):
        row = q // questions_per_row
        col = q % questions_per_row

        y1 = row * row_h
        y2 = (row + 1) * row_h if row < row_count - 1 else h
        x1 = col * col_w
        x2 = (col + 1) * col_w if col < questions_per_row - 1 else w

        detected = _detect_options_in_cell(binary, y1, y2, x1, x2, options, allow_multiple)
        detected_sets.append(detected)

    details: list[dict[str, str]] = []
    correct_count = 0
    warnings: list[str] = []

    for idx, expected_set in enumerate(answer_key):
        detected_set = detected_sets[idx]
        is_correct = detected_set == expected_set
        if is_correct:
            correct_count += 1

        if not detected_set:
            result_text = "未识别"
        elif is_correct:
            result_text = "正确"
        else:
            result_text = "错误"

        details.append(
            {
                "question": str(idx + 1),
                "expected": _format_answer(expected_set),
                "detected": _format_answer(detected_set),
                "result": result_text,
            }
        )

    unresolved_count = sum(1 for d in details if d["detected"] == "未识别")
    if unresolved_count > total_questions * 0.3:
        warnings.append("未识别题目较多，建议检查“每行题数”、拍摄角度与光照。")

    score_percent = round((correct_count / total_questions) * 100, 2)
    result = GradeResult(
        total_questions=total_questions,
        correct_count=correct_count,
        score_percent=score_percent,
        detected_answers=[_format_answer(x) for x in detected_sets],
        answer_key=[_format_answer(x) for x in answer_key],
        details=details,
        method="long-sheet-grid",
        warnings=warnings,
    )
    return result.__dict__

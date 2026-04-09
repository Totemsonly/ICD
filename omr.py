from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import cv2
import numpy as np


@dataclass
class GradeResult:
    total_questions: int
    correct_count: int
    score_percent: float
    detected_answers: List[str]
    answer_key: List[str]
    details: List[Dict[str, str]]


def parse_answer_key(text: str, num_questions: int, options: int) -> List[str]:
    if not text.strip():
        raise ValueError("请输入正确答案，例如：A,B,C,D,A")

    candidates = [x.strip().upper() for x in text.replace("，", ",").split(",") if x.strip()]
    if len(candidates) != num_questions:
        raise ValueError(f"答案数量与题目数量不一致：需要 {num_questions} 个，实际 {len(candidates)} 个。")

    valid_options = [chr(ord("A") + i) for i in range(options)]
    for idx, c in enumerate(candidates, start=1):
        if c not in valid_options:
            raise ValueError(f"第 {idx} 题答案 '{c}' 无效，可选范围：{','.join(valid_options)}")

    return candidates


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
    edge = cv2.Canny(blur, 60, 180)

    contours, _ = cv2.findContours(edge, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    paper = None
    for contour in contours[:10]:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            paper = approx
            break

    if paper is None:
        return image

    rect = _sort_points(paper)
    (tl, tr, br, bl) = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))

    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype="float32",
    )

    m = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, m, (max_w, max_h))
    return warped


def grade_answer_sheet(image_path: str, answer_key: List[str], options: int = 4) -> Dict[str, object]:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("无法读取图片，请确认上传的是有效图像文件。")

    warped = _warp_paper(image)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    questions = len(answer_key)
    if questions == 0:
        raise ValueError("答案不能为空。")

    h, w = thresh.shape
    box_h = h // questions
    box_w = w // options

    if box_h <= 0 or box_w <= 0:
        raise ValueError("题目数量或选项数量过大，请调整后重试。")

    detected_answers: List[str] = []
    details: List[Dict[str, str]] = []
    correct_count = 0

    for q in range(questions):
        y1 = q * box_h
        y2 = (q + 1) * box_h if q < questions - 1 else h

        pixel_counts = []
        for o in range(options):
            x1 = o * box_w
            x2 = (o + 1) * box_w if o < options - 1 else w

            roi = thresh[y1:y2, x1:x2]
            total = int(cv2.countNonZero(roi))
            pixel_counts.append(total)

        best_idx = int(np.argmax(pixel_counts))
        sorted_counts = sorted(pixel_counts, reverse=True)

        if sorted_counts[0] == 0 or (len(sorted_counts) > 1 and sorted_counts[0] < sorted_counts[1] * 1.15):
            picked = "未识别"
        else:
            picked = chr(ord("A") + best_idx)

        detected_answers.append(picked)

        expected = answer_key[q]
        is_correct = picked == expected
        if is_correct:
            correct_count += 1

        details.append(
            {
                "question": str(q + 1),
                "expected": expected,
                "detected": picked,
                "result": "正确" if is_correct else "错误",
            }
        )

    score_percent = (correct_count / questions) * 100

    result = GradeResult(
        total_questions=questions,
        correct_count=correct_count,
        score_percent=round(score_percent, 2),
        detected_answers=detected_answers,
        answer_key=answer_key,
        details=details,
    )
    return result.__dict__

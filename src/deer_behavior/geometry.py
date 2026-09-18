from __future__ import annotations

from math import hypot

Box = tuple[int, int, int, int]


def clamp_box(box: Box, width: int, height: int) -> Box:
    x1, y1, x2, y2 = box
    return (
        max(0, min(width - 1, x1)),
        max(0, min(height - 1, y1)),
        max(0, min(width - 1, x2)),
        max(0, min(height - 1, y2)),
    )


def box_area(box: Box) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def box_iou(left: Box, right: Box) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    ix1, iy1 = max(lx1, rx1), max(ly1, ry1)
    ix2, iy2 = min(lx2, rx2), min(ly2, ry2)
    inter = box_area((ix1, iy1, ix2, iy2))
    if inter <= 0:
        return 0.0
    union = box_area(left) + box_area(right) - inter
    return inter / union if union > 0 else 0.0


def box_center(box: Box) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def center_distance(left: Box, right: Box) -> float:
    lx, ly = box_center(left)
    rx, ry = box_center(right)
    return hypot(lx - rx, ly - ry)


def box_diagonal(box: Box) -> float:
    x1, y1, x2, y2 = box
    return hypot(max(1, x2 - x1), max(1, y2 - y1))

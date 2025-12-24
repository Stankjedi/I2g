"""
Grid detector module for automatic spritesheet grid detection.
Uses Pillow to analyze images and estimate grid dimensions.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

from .config import GridConfig
from .models import DetectionResult

_CACHE: dict[tuple[str, int, float], DetectionResult] = {}
_CACHE_HITS = 0
_CACHE_MISSES = 0


def _cache_key(path: Path) -> Optional[tuple[str, int, float]]:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), st.st_size, st.st_mtime)


def _cache_info() -> dict[str, int]:
    return {"hits": _CACHE_HITS, "misses": _CACHE_MISSES, "size": len(_CACHE)}


def _clear_cache() -> None:
    global _CACHE_HITS, _CACHE_MISSES
    _CACHE.clear()
    _CACHE_HITS = 0
    _CACHE_MISSES = 0


class GridDetector:
    """Detects spritesheet grid dimensions from image analysis."""

    def __init__(self, bg_tolerance: int = 10, gap_threshold: float = 0.95, sample_target: int = 128):
        self.bg_tolerance = bg_tolerance
        self.gap_threshold = gap_threshold
        self.sample_target = sample_target

    def _find_gaps_region(
        self,
        px,
        *,
        x0: int,
        x1: int,
        y0: int,
        y1: int,
        bg_color: Tuple,
        horizontal: bool,
    ) -> List[int]:
        gaps: list[int] = []
        threshold = self.gap_threshold

        region_w = max(0, x1 - x0)
        region_h = max(0, y1 - y0)
        if region_w == 0 or region_h == 0:
            return gaps

        if horizontal:
            step = max(1, region_w // self.sample_target)
            sample_count = (region_w + step - 1) // step
            allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

            for y in range(y0, y1):
                non_bg = 0
                for x in range(x0, x1, step):
                    if not self._is_background(px[x, y], bg_color):
                        non_bg += 1
                        if non_bg > allowed_non_bg:
                            break
                if non_bg <= allowed_non_bg:
                    gaps.append(y)

        else:
            step = max(1, region_h // self.sample_target)
            sample_count = (region_h + step - 1) // step
            allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

            for x in range(x0, x1):
                non_bg = 0
                for y in range(y0, y1, step):
                    if not self._is_background(px[x, y], bg_color):
                        non_bg += 1
                        if non_bg > allowed_non_bg:
                            break
                if non_bg <= allowed_non_bg:
                    gaps.append(x)

        return gaps

    def _count_edge_gap_lines(self, px, width: int, height: int, bg_color: Tuple, *, horizontal: bool, reverse: bool) -> int:
        threshold = self.gap_threshold
        count = 0

        if horizontal:
            step = max(1, width // self.sample_target)
            sample_count = (width + step - 1) // step
            allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

            ys = range(height - 1, -1, -1) if reverse else range(height)
            for y in ys:
                non_bg = 0
                for x in range(0, width, step):
                    if not self._is_background(px[x, y], bg_color):
                        non_bg += 1
                        if non_bg > allowed_non_bg:
                            break
                if non_bg <= allowed_non_bg:
                    count += 1
                else:
                    break
            return count

        step = max(1, height // self.sample_target)
        sample_count = (height + step - 1) // step
        allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

        xs = range(width - 1, -1, -1) if reverse else range(width)
        for x in xs:
            non_bg = 0
            for y in range(0, height, step):
                if not self._is_background(px[x, y], bg_color):
                    non_bg += 1
                    if non_bg > allowed_non_bg:
                        break
            if non_bg <= allowed_non_bg:
                count += 1
            else:
                break
        return count

    def _group_gaps(self, gaps: List[int]) -> List[Tuple[int, int]]:
        if not gaps:
            return []

        groups: list[tuple[int, int]] = []
        start = gaps[0]
        end = gaps[0]

        for g in gaps[1:]:
            if g - end <= 3:
                end = g
            else:
                groups.append((start, end))
                start = g
                end = g

        groups.append((start, end))
        return groups

    @staticmethod
    def _median_int(values: List[int]) -> int:
        values = [v for v in values if v >= 0]
        if not values:
            return 0
        values.sort()
        return values[len(values) // 2]

    def detect(self, image_path: Path) -> DetectionResult:
        """
        Detect grid configuration from an image.
        Uses background color detection and gap analysis.
        """
        try:
            from PIL import Image
        except ImportError:
            return DetectionResult(
                detected=False,
                notes=["Pillow not installed, cannot detect grid"],
            )

        try:
            with Image.open(image_path) as img:
                img = img.convert("RGBA")
                width, height = img.size
                px = img.load()

                bg_color = self._detect_background_color(px, width, height)

                notes: list[str] = []

                h_gaps = self._find_gaps(px, width, height, bg_color, horizontal=True)
                v_gaps = self._find_gaps(px, width, height, bg_color, horizontal=False)

                rows, row_height = self._estimate_grid_from_gaps(h_gaps, height)
                cols, col_width = self._estimate_grid_from_gaps(v_gaps, width)

                offset_x = 0
                offset_y = 0
                pad_x = 0
                pad_y = 0

                # Estimate offsets/padding by trimming background-only borders and analyzing gap groups.
                top_trim = self._count_edge_gap_lines(px, width, height, bg_color, horizontal=True, reverse=False)
                bottom_trim = self._count_edge_gap_lines(px, width, height, bg_color, horizontal=True, reverse=True)
                left_trim = self._count_edge_gap_lines(px, width, height, bg_color, horizontal=False, reverse=False)
                right_trim = self._count_edge_gap_lines(px, width, height, bg_color, horizontal=False, reverse=True)

                x0 = left_trim
                x1 = width - right_trim
                y0 = top_trim
                y1 = height - bottom_trim

                if x0 < x1 and y0 < y1 and (top_trim or bottom_trim or left_trim or right_trim or h_gaps or v_gaps):
                    h_gaps_region = self._find_gaps_region(
                        px,
                        x0=x0,
                        x1=x1,
                        y0=y0,
                        y1=y1,
                        bg_color=bg_color,
                        horizontal=True,
                    )
                    v_gaps_region = self._find_gaps_region(
                        px,
                        x0=x0,
                        x1=x1,
                        y0=y0,
                        y1=y1,
                        bg_color=bg_color,
                        horizontal=False,
                    )

                    h_groups = self._group_gaps(h_gaps_region)
                    v_groups = self._group_gaps(v_gaps_region)

                    cand_rows = len(h_groups) + 1 if h_groups else 1
                    cand_cols = len(v_groups) + 1 if v_groups else 1

                    pad_y_cand = self._median_int([end - start + 1 for start, end in h_groups]) if h_groups else 0
                    pad_x_cand = self._median_int([end - start + 1 for start, end in v_groups]) if v_groups else 0

                    def segments(start: int, end: int, groups: List[Tuple[int, int]]) -> List[int]:
                        out: list[int] = []
                        cursor = start
                        for s, e in groups:
                            out.append(s - cursor)
                            cursor = e + 1
                        out.append(end - cursor)
                        return out

                    frame_heights = segments(y0, y1, h_groups)
                    frame_widths = segments(x0, x1, v_groups)

                    if (
                        cand_rows >= 1
                        and cand_cols >= 1
                        and len(frame_heights) == cand_rows
                        and len(frame_widths) == cand_cols
                        and min(frame_heights) > 0
                        and min(frame_widths) > 0
                    ):
                        # Use the refined geometry when it is consistent.
                        offset_x = left_trim
                        offset_y = top_trim
                        pad_x = max(0, pad_x_cand)
                        pad_y = max(0, pad_y_cand)

                        if cand_rows > 1 and cand_cols > 1:
                            rows = cand_rows
                            cols = cand_cols
                            row_height = self._median_int(frame_heights)
                            col_width = self._median_int(frame_widths)
                            if offset_x or offset_y or pad_x or pad_y:
                                notes.append(
                                    f"estimated offsets/padding: offset=({offset_x},{offset_y}) pad=({pad_x},{pad_y})"
                                )
                    else:
                        notes.append("offset/padding estimation not confident; using defaults")

                if rows <= 1 or cols <= 1:
                    rows, cols, row_height, col_width = self._try_common_grids(width, height)

                confidence = self._calculate_confidence(h_gaps, v_gaps, rows, cols, width, height)

                grid = GridConfig(rows=rows, cols=cols, offset_x=offset_x, offset_y=offset_y, pad_x=pad_x, pad_y=pad_y)

                return DetectionResult(
                    detected=True,
                    grid=grid,
                    confidence=confidence,
                    image_width=width,
                    image_height=height,
                    frame_width=col_width,
                    frame_height=row_height,
                    method="gap_analysis" if h_gaps or v_gaps else "common_grid",
                    notes=notes,
                )

        except Exception as e:
            return DetectionResult(detected=False, notes=[f"Error analyzing image: {str(e)}"])

    def _detect_background_color(self, px, width: int, height: int) -> Tuple[int, int, int, int]:
        """Detect background color from image corners."""
        corners = [
            px[0, 0],
            px[width - 1, 0],
            px[0, height - 1],
            px[width - 1, height - 1],
        ]

        color_counts: dict[tuple[int, int, int], int] = {}
        for c in corners:
            key = (int(c[0]), int(c[1]), int(c[2]))
            color_counts[key] = color_counts.get(key, 0) + 1

        r, g, b = max(color_counts.items(), key=lambda x: x[1])[0]

        for c in corners:
            if (int(c[0]), int(c[1]), int(c[2])) == (r, g, b):
                a = int(c[3]) if len(c) > 3 else 255
                return (r, g, b, a)

        return (r, g, b, 255)

    def _is_background(self, pixel: Tuple[int, int, int, int], bg_color: Tuple[int, int, int, int]) -> bool:
        """Check if a pixel matches the background color."""
        a = int(pixel[3]) if len(pixel) > 3 else 255
        if a < 10:
            return True

        r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
        if abs(r - bg_color[0]) > self.bg_tolerance:
            return False
        if abs(g - bg_color[1]) > self.bg_tolerance:
            return False
        if abs(b - bg_color[2]) > self.bg_tolerance:
            return False
        return True

    def _find_gaps(self, px, width: int, height: int, bg_color: Tuple, horizontal: bool) -> List[int]:
        """Find potential gap lines (mostly background pixels)."""
        gaps: list[int] = []
        threshold = self.gap_threshold

        if horizontal:
            step = max(1, width // self.sample_target)
            sample_count = (width + step - 1) // step
            allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

            for y in range(height):
                non_bg = 0
                for x in range(0, width, step):
                    if not self._is_background(px[x, y], bg_color):
                        non_bg += 1
                        if non_bg > allowed_non_bg:
                            break
                if non_bg <= allowed_non_bg:
                    gaps.append(y)

        else:
            step = max(1, height // self.sample_target)
            sample_count = (height + step - 1) // step
            allowed_non_bg = max(0, int(math.floor(sample_count * (1.0 - threshold))))

            for x in range(width):
                non_bg = 0
                for y in range(0, height, step):
                    if not self._is_background(px[x, y], bg_color):
                        non_bg += 1
                        if non_bg > allowed_non_bg:
                            break
                if non_bg <= allowed_non_bg:
                    gaps.append(x)

        return gaps

    def _estimate_grid_from_gaps(self, gaps: List[int], total_size: int) -> Tuple[int, int]:
        """Estimate grid count and cell size from gap positions."""
        if not gaps:
            return 1, total_size

        gap_groups: list[list[int]] = []
        current_group = [gaps[0]]

        for gap in gaps[1:]:
            if gap - current_group[-1] <= 3:
                current_group.append(gap)
            else:
                gap_groups.append(current_group)
                current_group = [gap]
        gap_groups.append(current_group)

        cells = len(gap_groups) + 1
        if cells > 1:
            cell_size = total_size // cells
            return cells, cell_size

        return 1, total_size

    def _try_common_grids(self, width: int, height: int) -> Tuple[int, int, int, int]:
        """Try common sprite sheet grid sizes."""
        common = [
            (1, 4),
            (1, 6),
            (1, 8),
            (1, 12),
            (4, 1),
            (6, 1),
            (8, 1),
            (2, 2),
            (2, 4),
            (4, 2),
            (3, 4),
            (4, 3),
            (4, 4),
            (3, 3),
            (5, 5),
        ]

        best_score = 0.0
        best_grid = (1, 1)

        for rows, cols in common:
            if width % cols == 0 and height % rows == 0:
                cell_w = width // cols
                cell_h = height // rows

                aspect_ratio = cell_w / cell_h if cell_h > 0 else 0
                score = 1.0 / (abs(aspect_ratio - 1.0) + 0.1)

                frame_count = rows * cols
                if frame_count in [4, 6, 8, 12, 16]:
                    score *= 1.5

                if score > best_score:
                    best_score = score
                    best_grid = (rows, cols)

        rows, cols = best_grid
        return rows, cols, height // rows, width // cols

    def _calculate_confidence(
        self,
        h_gaps: List[int],
        v_gaps: List[int],
        rows: int,
        cols: int,
        width: int,
        height: int,
    ) -> float:
        confidence = 0.5
        if h_gaps:
            confidence += 0.2
        if v_gaps:
            confidence += 0.2
        if cols and width % cols == 0:
            confidence += 0.05
        if rows and height % rows == 0:
            confidence += 0.05
        return min(confidence, 1.0)


def detect_grid(image_path: Path) -> DetectionResult:
    """Convenience function to detect grid from image."""
    global _CACHE_HITS, _CACHE_MISSES

    key = _cache_key(image_path)
    if key is not None:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE_HITS += 1
            return cached

    _CACHE_MISSES += 1
    detector = GridDetector()
    result = detector.detect(image_path)

    if key is not None:
        if len(_CACHE) > 256:
            _CACHE.clear()
        _CACHE[key] = result

    return result

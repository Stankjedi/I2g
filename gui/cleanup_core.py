"""
cleanup_core.py
Python implementation of the background cleanup algorithm.
No Aseprite dependency - uses Pillow for image processing.
"""

from collections import deque
import time
from typing import Callable, Tuple

from PIL import Image


class CancelledError(Exception):
    pass


def get_brightness(r: int, g: int, b: int) -> float:
    """Calculate perceived brightness of a color."""
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_outline(pixel: Tuple[int, ...], threshold: int) -> bool:
    """Check if pixel is a dark outline."""
    if len(pixel) == 4 and pixel[3] < 128:  # Transparent
        return False
    r, g, b = pixel[:3]
    return get_brightness(r, g, b) <= threshold


def is_similar(p1: Tuple[int, ...], p2: Tuple[int, ...], tolerance: int) -> bool:
    """Check if two pixels are similar in color."""
    a1 = p1[3] if len(p1) == 4 else 255
    a2 = p2[3] if len(p2) == 4 else 255

    if a1 < 10 and a2 < 10:
        return True
    if (a1 < 10) != (a2 < 10):
        return False

    return (
        abs(p1[0] - p2[0]) <= tolerance
        and abs(p1[1] - p2[1]) <= tolerance
        and abs(p1[2] - p2[2]) <= tolerance
    )


def is_greenish(pixel: Tuple[int, ...]) -> bool:
    """Check if pixel has green tint (for edge remnant detection)."""
    if len(pixel) == 4 and pixel[3] < 10:
        return False
    r, g, b = pixel[:3]
    a = pixel[3] if len(pixel) == 4 else 255
    # Green dominant or semi-transparent
    return (g > r - 15 and g > b - 15 and g > 20) or (a < 200)


def _cleanup_background_core(
    image: Image.Image,
    outline_threshold: int,
    fill_tolerance: int,
    dilation_passes: int,
    progress_callback: Callable[[int, str], None] | None,
    cancel_check: Callable[[], bool] | None,
) -> Tuple[Image.Image, dict]:
    start_time = time.time()

    def check_cancel() -> None:
        if cancel_check and cancel_check():
            raise CancelledError()

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    img = image.copy()
    pixels = img.load()
    w, h = img.size
    size = w * h

    removed = bytearray(size)
    pixels_to_remove = []

    check_cancel()

    if progress_callback:
        progress_callback(5, "Flood fill from edges...")

    visited = bytearray(size)
    queue = deque()

    for x in range(w):
        queue.append((x, 0))
        queue.append((x, h - 1))
    for y in range(1, h - 1):
        queue.append((0, y))
        queue.append((w - 1, y))

    corner_pixels = [
        pixels[0, 0],
        pixels[w - 1, 0],
        pixels[0, h - 1],
        pixels[w - 1, h - 1],
    ]

    while queue:
        check_cancel()
        x, y = queue.popleft()

        if x < 0 or x >= w or y < 0 or y >= h:
            continue
        idx = y * w + x
        if visited[idx]:
            continue
        visited[idx] = 1

        px = pixels[x, y]

        if is_outline(px, outline_threshold):
            continue

        match_bg = any(is_similar(px, cpx, fill_tolerance) for cpx in corner_pixels)

        alpha = px[3] if len(px) == 4 else 255
        if match_bg or alpha < 128:
            pixels_to_remove.append((x, y))
            removed[idx] = 1
            queue.append((x - 1, y))
            queue.append((x + 1, y))
            queue.append((x, y - 1))
            queue.append((x, y + 1))

    if progress_callback:
        progress_callback(40, "Edge dilation...")

    edge_removed = 0
    neighbors_8 = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ]

    protected = bytearray(size)
    for y in range(h):
        row_offset = y * w
        for x in range(w):
            px = pixels[x, y]
            if is_outline(px, outline_threshold):
                protected[row_offset + x] = 1

    if dilation_passes > 0:
        frontier = set()

        for y in range(h):
            check_cancel()
            row_offset = y * w
            for x in range(w):
                idx = row_offset + x
                if removed[idx] or protected[idx]:
                    continue

                for dx, dy in neighbors_8:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and removed[ny * w + nx]:
                        frontier.add((x, y))
                        break

        for pass_num in range(dilation_passes):
            check_cancel()
            if not frontier:
                break

            new_removals = []
            new_frontier = set()

            for x, y in frontier:
                idx = y * w + x
                if removed[idx] or protected[idx]:
                    continue

                px = pixels[x, y]
                alpha = px[3] if len(px) == 4 else 255

                is_bg_like = alpha < 200
                if not is_bg_like and is_greenish(px):
                    is_bg_like = True
                if not is_bg_like:
                    for cpx in corner_pixels:
                        if is_similar(px, cpx, fill_tolerance):
                            is_bg_like = True
                            break

                if is_bg_like:
                    new_removals.append((x, y))

            for x, y in new_removals:
                idx = y * w + x
                removed[idx] = 1
                pixels_to_remove.append((x, y))
                edge_removed += 1

                for dx, dy in neighbors_8:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        nidx = ny * w + nx
                        if not removed[nidx] and not protected[nidx]:
                            new_frontier.add((nx, ny))

            if not new_removals:
                break

            frontier = new_frontier

            if progress_callback:
                progress = 40 + int(40 * (pass_num + 1) / dilation_passes)
                progress_callback(progress, f"Edge dilation pass {pass_num + 1}...")

    if progress_callback:
        progress_callback(85, "Final cleanup...")

    isolated_removed = 0
    for y in range(h):
        check_cancel()
        row_offset = y * w
        for x in range(w):
            idx = row_offset + x
            if removed[idx]:
                continue

            px = pixels[x, y]
            if is_outline(px, outline_threshold):
                continue
            if not is_greenish(px):
                continue

            adj_outline = False
            adj_transparent = False

            for dx, dy in neighbors_8:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if removed[ny * w + nx]:
                        adj_transparent = True
                    else:
                        npx = pixels[nx, ny]
                        if is_outline(npx, outline_threshold):
                            adj_outline = True
                        if len(npx) == 4 and npx[3] < 50:
                            adj_transparent = True
                else:
                    adj_transparent = True

            if adj_outline and adj_transparent:
                pixels_to_remove.append((x, y))
                removed[idx] = 1
                isolated_removed += 1

    check_cancel()

    if progress_callback:
        progress_callback(95, "Applying changes...")

    for x, y in pixels_to_remove:
        pixels[x, y] = (0, 0, 0, 0)

    elapsed = time.time() - start_time

    stats = {
        "pixels_removed": len(pixels_to_remove),
        "edge_pixels_removed": edge_removed,
        "isolated_pixels_removed": isolated_removed,
        "image_width": w,
        "image_height": h,
        "total_pixels": w * h,
        "removal_percentage": (len(pixels_to_remove) / (w * h)) * 100,
        "processing_time_ms": elapsed * 1000,
        "outline_threshold": outline_threshold,
        "dilation_passes": dilation_passes,
    }

    if progress_callback:
        progress_callback(100, "Complete!")

    return img, stats


def cleanup_background(
    image: Image.Image,
    outline_threshold: int = 20,
    fill_tolerance: int = 80,
    dilation_passes: int = 50,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Tuple[Image.Image, dict]:
    """
    Remove background outside of dark outlines.

    Args:
        image: Input PIL Image (RGBA)
        outline_threshold: Brightness threshold for outline detection (0-255)
        fill_tolerance: Color similarity tolerance for flood fill
        dilation_passes: Number of edge dilation passes
        progress_callback: Optional callback(percent, message) for progress updates

    Returns:
        Tuple of (cleaned image, stats dict)
    """
    start_time = time.time()
    if cancel_check and cancel_check():
        raise CancelledError()

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    w, h = image.size
    min_dim = min(w, h)
    scale_factor = 1
    effective_dilation = dilation_passes

    if min_dim < 192:
        target = 192
        max_scale = 6
        scale_factor = min(max_scale, max(1, int(round(target / max(1, min_dim)))))
        if scale_factor > 1:
            scaled = image.resize((w * scale_factor, h * scale_factor), Image.Resampling.NEAREST)
            effective_dilation = min(dilation_passes, max(8, min_dim // 4))
            cleaned_scaled, _ = _cleanup_background_core(
                scaled,
                outline_threshold,
                fill_tolerance,
                effective_dilation,
                progress_callback,
                cancel_check,
            )
            mask = cleaned_scaled.getchannel("A")
            mask_small = mask.resize((w, h), Image.Resampling.NEAREST)
            mask_px = mask_small.load()
            result = image.copy()
            res_px = result.load()
            removed_count = 0
            for y in range(h):
                for x in range(w):
                    if mask_px[x, y] == 0:
                        res_px[x, y] = (0, 0, 0, 0)
                        removed_count += 1

            elapsed = time.time() - start_time
            stats = {
                "pixels_removed": removed_count,
                "edge_pixels_removed": 0,
                "isolated_pixels_removed": 0,
                "image_width": w,
                "image_height": h,
                "total_pixels": w * h,
                "removal_percentage": (removed_count / (w * h)) * 100,
                "processing_time_ms": elapsed * 1000,
                "outline_threshold": outline_threshold,
                "dilation_passes": effective_dilation,
                "scale_factor": scale_factor,
                "scaled_cleanup": True,
            }
            return result, stats

    result, stats = _cleanup_background_core(
        image,
        outline_threshold,
        fill_tolerance,
        dilation_passes,
        progress_callback,
        cancel_check,
    )
    stats["scale_factor"] = 1
    stats["scaled_cleanup"] = False
    return result, stats

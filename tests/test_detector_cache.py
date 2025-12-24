from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.detector import _cache_info, _clear_cache, detect_grid


def test_detect_grid_cache_hits(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")

    _clear_cache()

    image_path = tmp_path / "sheet.png"
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))

    # Simple 2x2 with a 1px gap line (same construction as other detector test).
    for y in range(10):
        for x in range(10):
            if x == 5 or y == 5:
                continue
            img.putpixel((x, y), (255, 0, 0, 255))

    img.save(image_path)

    detect_grid(image_path)
    before = _cache_info()
    detect_grid(image_path)
    after = _cache_info()

    assert after["hits"] == before["hits"] + 1

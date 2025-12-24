from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.detector import detect_grid


def test_detect_grid_simple_2x2(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")

    image_path = tmp_path / "sheet.png"
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))

    # Create 2x2 quadrants separated by a 1px transparent gap line at x=5 and y=5.
    for y in range(10):
        for x in range(10):
            if x == 5 or y == 5:
                continue
            if x < 5 and y < 5:
                img.putpixel((x, y), (255, 0, 0, 255))
            elif x > 5 and y < 5:
                img.putpixel((x, y), (0, 255, 0, 255))
            elif x < 5 and y > 5:
                img.putpixel((x, y), (0, 0, 255, 255))
            else:
                img.putpixel((x, y), (255, 255, 0, 255))

    img.save(image_path)

    result = detect_grid(image_path)
    assert result.detected is True
    assert result.grid is not None
    assert result.grid.rows == 2
    assert result.grid.cols == 2

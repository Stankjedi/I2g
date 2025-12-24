from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.detector import detect_grid


def test_detect_grid_estimates_offsets_and_padding(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")

    rows = 3
    cols = 4
    frame_w = 10
    frame_h = 8
    pad = 2
    margin = 5

    width = margin * 2 + cols * frame_w + (cols - 1) * pad
    height = margin * 2 + rows * frame_h + (rows - 1) * pad

    image_path = tmp_path / "sheet_margin_pad.png"
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            x0 = margin + c * (frame_w + pad)
            y0 = margin + r * (frame_h + pad)
            draw.rectangle((x0, y0, x0 + frame_w - 1, y0 + frame_h - 1), fill=(0, 0, 0, 255))

    img.save(image_path)

    result = detect_grid(image_path)
    assert result.detected is True
    assert result.grid is not None
    assert result.grid.rows == rows
    assert result.grid.cols == cols
    assert result.grid.offset_x == margin
    assert result.grid.offset_y == margin
    assert result.grid.pad_x == pad
    assert result.grid.pad_y == pad

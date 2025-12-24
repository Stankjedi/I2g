from __future__ import annotations

import json
from pathlib import Path

import pytest

from ss_anim_mcp.postprocess import PostProcessor, extract_frames_from_sheet


def test_extract_frames_from_sheet_order(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")

    sheet_png = tmp_path / "anim_sheet.png"
    sheet_json = tmp_path / "anim_sheet.json"
    frames_dir = tmp_path / "frames"

    # Create a 4x2 sheet containing two 2x2 frames: red then green.
    sheet = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
    for y in range(2):
        for x in range(2):
            sheet.putpixel((x, y), (255, 0, 0, 255))
            sheet.putpixel((x + 2, y), (0, 255, 0, 255))
    sheet.save(sheet_png)

    sheet_json.write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "frame": {"x": 0, "y": 0, "w": 2, "h": 2},
                        "sourceSize": {"w": 2, "h": 2},
                        "spriteSourceSize": {"x": 0, "y": 0, "w": 2, "h": 2},
                    },
                    {
                        "frame": {"x": 2, "y": 0, "w": 2, "h": 2},
                        "sourceSize": {"w": 2, "h": 2},
                        "spriteSourceSize": {"x": 0, "y": 0, "w": 2, "h": 2},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    frames = extract_frames_from_sheet(sheet_png, sheet_json, frames_dir)
    assert [p.name for p in frames] == ["frame_0000.png", "frame_0001.png"]

    with Image.open(frames[0]) as f0:
        assert f0.size == (2, 2)
        assert f0.getpixel((0, 0))[:3] == (255, 0, 0)

    with Image.open(frames[1]) as f1:
        assert f1.size == (2, 2)
        assert f1.getpixel((0, 0))[:3] == (0, 255, 0)


@pytest.mark.asyncio
async def test_create_hq_gif_mocked_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Image = pytest.importorskip("PIL.Image")

    frame = tmp_path / "frame_0000.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(frame)

    out_gif = tmp_path / "out.gif"

    post = PostProcessor()
    post._ffmpeg_available = True  # force-enable in test

    async def fake_run_cmd(cmd: list[str]) -> int:
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".png":
            out_path.write_bytes(b"")
        else:
            out_path.write_bytes(b"GIF89a")
        return 0

    monkeypatch.setattr(post, "_run_cmd", fake_run_cmd)

    ok = await post.create_hq_gif([frame], out_gif, fps=12)
    assert ok is True
    assert out_gif.exists()

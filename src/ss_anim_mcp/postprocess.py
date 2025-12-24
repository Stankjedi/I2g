"""
Post-processing module for high-quality GIF generation.
Uses FFmpeg and gifsicle for optimal output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _frames_from_aseprite_json(data: dict) -> list[dict]:
    frames = data.get("frames")
    if isinstance(frames, list):
        return frames
    if isinstance(frames, dict):
        return [frames[k] for k in sorted(frames.keys())]
    raise ValueError("Unsupported Aseprite JSON format: missing 'frames'")


def extract_frames_from_sheet(
    sheet_png_path: Path,
    sheet_json_path: Path,
    frames_dir: Path,
    *,
    filename_prefix: str = "frame_",
) -> list[Path]:
    """
    Extract ordered frames from `anim_sheet.png` + `anim_sheet.json`.

    Supports both trimmed and untrimmed exports:
    - Uses `frame` rectangle to crop from the sheet.
    - If `sourceSize` + `spriteSourceSize` exist, reconstructs full-sized frames.
    """
    from PIL import Image

    data = json.loads(sheet_json_path.read_text(encoding="utf-8"))
    frame_entries = _frames_from_aseprite_json(data)

    frames_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []

    with Image.open(sheet_png_path) as sheet:
        sheet = sheet.convert("RGBA")

        for i, entry in enumerate(frame_entries):
            rect = entry.get("frame") or {}
            x = int(rect["x"])
            y = int(rect["y"])
            w = int(rect["w"])
            h = int(rect["h"])

            cropped = sheet.crop((x, y, x + w, y + h))

            source_size = entry.get("sourceSize")
            sprite_source = entry.get("spriteSourceSize")

            if isinstance(source_size, dict) and isinstance(sprite_source, dict):
                out_w = int(source_size["w"])
                out_h = int(source_size["h"])
                dst_x = int(sprite_source["x"])
                dst_y = int(sprite_source["y"])

                frame_img = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                frame_img.paste(cropped, (dst_x, dst_y))
            else:
                frame_img = cropped

            out_path = frames_dir / f"{filename_prefix}{i:04d}.png"
            frame_img.save(out_path)
            output_paths.append(out_path)

    return output_paths


class PostProcessor:
    """Handles post-processing for high-quality outputs."""

    def __init__(self):
        self._ffmpeg_available: Optional[bool] = None
        self._gifsicle_available: Optional[bool] = None

    @property
    def ffmpeg_available(self) -> bool:
        if self._ffmpeg_available is None:
            self._ffmpeg_available = shutil.which("ffmpeg") is not None
        return self._ffmpeg_available

    @property
    def gifsicle_available(self) -> bool:
        if self._gifsicle_available is None:
            self._gifsicle_available = shutil.which("gifsicle") is not None
        return self._gifsicle_available

    async def _run_cmd(self, cmd: list[str]) -> int:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode

    async def create_hq_gif(
        self,
        frames: list[Path],
        output_path: Path,
        fps: int = 12,
        loop: int = 0,
    ) -> bool:
        """
        Create high-quality GIF from PNG frames using FFmpeg palette optimization.

        Returns True if successful, False otherwise.
        """
        if not self.ffmpeg_available:
            return False
        if not frames:
            return False

        temp_dir = output_path.parent / ".hq_gif_temp"

        try:
            temp_dir.mkdir(exist_ok=True)

            input_list = temp_dir / "input.txt"
            with input_list.open("w", encoding="utf-8") as f:
                duration = 1.0 / fps
                for frame in frames:
                    f.write(f"file '{frame.absolute()}'\n")
                    f.write(f"duration {duration}\n")
                f.write(f"file '{frames[-1].absolute()}'\n")

            palette_path = temp_dir / "palette.png"
            palette_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(input_list),
                "-vf",
                "palettegen=stats_mode=diff",
                str(palette_path),
            ]

            rc = await self._run_cmd(palette_cmd)
            if rc != 0 or not palette_path.exists():
                return False

            gif_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(input_list),
                "-i",
                str(palette_path),
                "-lavfi",
                "paletteuse=dither=bayer:bayer_scale=5",
                "-loop",
                str(loop),
                str(output_path),
            ]

            rc = await self._run_cmd(gif_cmd)
            if rc != 0:
                return False

            if self.gifsicle_available and output_path.exists():
                await self.optimize_gif(output_path)

            return output_path.exists()

        except Exception:
            logger.exception("HQ GIF creation failed")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def optimize_gif(self, gif_path: Path) -> bool:
        """Optimize GIF using gifsicle (best-effort)."""
        if not self.gifsicle_available:
            return False

        try:
            temp_path = gif_path.with_suffix(".optimized.gif")
            cmd = [
                "gifsicle",
                "-O3",
                "--colors",
                "256",
                str(gif_path),
                "-o",
                str(temp_path),
            ]

            rc = await self._run_cmd(cmd)
            if rc == 0 and temp_path.exists():
                temp_path.replace(gif_path)
                return True

            temp_path.unlink(missing_ok=True)
            return False

        except Exception:
            logger.exception("GIF optimization failed")
            return False


_post_processor: Optional[PostProcessor] = None


def get_post_processor() -> PostProcessor:
    """Get or create global PostProcessor instance."""
    global _post_processor
    if _post_processor is None:
        _post_processor = PostProcessor()
    return _post_processor


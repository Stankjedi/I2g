"""
Post-processing module for high-quality GIF generation.
Uses FFmpeg and gifsicle for optimal output.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional, List


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
    
    async def create_hq_gif(
        self,
        frames: List[Path],
        output_path: Path,
        fps: int = 12,
        loop: int = 0,
    ) -> bool:
        """
        Create high-quality GIF from PNG frames using FFmpeg palette optimization.
        
        Args:
            frames: List of PNG frame paths in order
            output_path: Output GIF path
            fps: Frames per second
            loop: Loop count (0 = infinite)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.ffmpeg_available:
            return False
        
        if not frames:
            return False
        
        try:
            # Create temporary directory for processing
            temp_dir = output_path.parent / ".hq_gif_temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Create input file list for FFmpeg
            input_list = temp_dir / "input.txt"
            with open(input_list, "w") as f:
                for frame in frames:
                    # Duration in seconds
                    duration = 1.0 / fps
                    f.write(f"file '{frame.absolute()}'\n")
                    f.write(f"duration {duration}\n")
                # Add last frame again for proper duration
                f.write(f"file '{frames[-1].absolute()}'\n")
            
            # Step 1: Generate optimized palette
            palette_path = temp_dir / "palette.png"
            
            palette_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(input_list),
                "-vf", "palettegen=stats_mode=diff",
                str(palette_path),
            ]
            
            process = await asyncio.create_subprocess_exec(
                *palette_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            
            if process.returncode != 0 or not palette_path.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False
            
            # Step 2: Generate GIF using palette
            gif_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(input_list),
                "-i", str(palette_path),
                "-lavfi", "paletteuse=dither=bayer:bayer_scale=5",
                "-loop", str(loop),
                str(output_path),
            ]
            
            process = await asyncio.create_subprocess_exec(
                *gif_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            if process.returncode != 0:
                return False
            
            # Step 3: Optimize with gifsicle if available
            if self.gifsicle_available and output_path.exists():
                await self.optimize_gif(output_path)
            
            return output_path.exists()
            
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    
    async def optimize_gif(self, gif_path: Path) -> bool:
        """
        Optimize GIF using gifsicle.
        
        Args:
            gif_path: Path to GIF to optimize (modified in place)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.gifsicle_available:
            return False
        
        try:
            temp_path = gif_path.with_suffix(".optimized.gif")
            
            cmd = [
                "gifsicle",
                "-O3",  # Maximum optimization
                "--colors", "256",
                str(gif_path),
                "-o", str(temp_path),
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            
            if process.returncode == 0 and temp_path.exists():
                # Replace original with optimized version
                temp_path.replace(gif_path)
                return True
            else:
                temp_path.unlink(missing_ok=True)
                return False
                
        except Exception:
            return False
    
    async def create_gif_from_frames(
        self,
        frame_dir: Path,
        output_path: Path,
        fps: int = 12,
        pattern: str = "frame_*.png",
    ) -> bool:
        """
        Create GIF from frames in a directory.
        
        Args:
            frame_dir: Directory containing frame images
            output_path: Output GIF path
            fps: Frames per second
            pattern: Glob pattern for frame files
        
        Returns:
            True if successful, False otherwise
        """
        frames = sorted(frame_dir.glob(pattern))
        if not frames:
            return False
        
        return await self.create_hq_gif(frames, output_path, fps)


# Global instance
_post_processor: Optional[PostProcessor] = None


def get_post_processor() -> PostProcessor:
    """Get or create global PostProcessor instance."""
    global _post_processor
    if _post_processor is None:
        _post_processor = PostProcessor()
    return _post_processor

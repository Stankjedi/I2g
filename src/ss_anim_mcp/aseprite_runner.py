"""
Aseprite CLI runner module.
Handles subprocess execution of Aseprite in batch mode with Lua scripts.
"""

import asyncio
import subprocess
import json
import shutil
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

from .config import Settings, get_settings, ConversionProfile
from .models import JobSpec, ConvertResult, QualityMetrics, AnchorInfo


class AsepriteError(Exception):
    """Exception raised when Aseprite execution fails."""
    def __init__(self, message: str, stderr: str = "", returncode: int = -1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class AsepriteRunner:
    """Runs Aseprite CLI with Lua scripts for conversion."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._validate_aseprite()
    
    def _validate_aseprite(self) -> None:
        """Check if Aseprite executable exists."""
        if not self.settings.aseprite_exe.exists():
            # Check if it's in PATH
            if shutil.which(str(self.settings.aseprite_exe)) is None:
                raise AsepriteError(
                    f"Aseprite executable not found: {self.settings.aseprite_exe}\n"
                    "Set ASEPRITE_EXE environment variable to the correct path."
                )
    
    def is_available(self) -> bool:
        """Check if Aseprite is available."""
        try:
            self._validate_aseprite()
            return True
        except AsepriteError:
            return False
    
    def _build_script_params(
        self,
        job: JobSpec,
        profile: ConversionProfile,
        output_dir: Path,
    ) -> list[str]:
        """Build --script-param arguments for Aseprite CLI."""
        # Merge job overrides with profile
        grid = job.grid or profile.grid
        timing = job.timing or profile.timing
        anchor = job.anchor or profile.anchor
        background = job.background or profile.background
        export = job.export or profile.export
        
        params = [
            f"--script-param", f"input_path={job.input_path}",
            f"--script-param", f"output_dir={output_dir}",
            f"--script-param", f"job_name={job.job_name}",
            
            # Grid params
            f"--script-param", f"grid_rows={grid.rows}",
            f"--script-param", f"grid_cols={grid.cols}",
            f"--script-param", f"grid_offset_x={grid.offset_x}",
            f"--script-param", f"grid_offset_y={grid.offset_y}",
            f"--script-param", f"grid_pad_x={grid.pad_x}",
            f"--script-param", f"grid_pad_y={grid.pad_y}",
            
            # Timing params
            f"--script-param", f"fps={timing.fps}",
            f"--script-param", f"loop_mode={timing.loop_mode}",
            
            # Anchor params
            f"--script-param", f"anchor_mode={anchor.mode}",
            f"--script-param", f"anchor_alpha_thresh={anchor.alpha_thresh}",
            
            # Background params
            f"--script-param", f"bg_mode={background.mode}",
            f"--script-param", f"bg_color_r={background.color[0]}",
            f"--script-param", f"bg_color_g={background.color[1]}",
            f"--script-param", f"bg_color_b={background.color[2]}",
            f"--script-param", f"bg_tolerance={background.tolerance}",
            
            # Export params
            f"--script-param", f"export_aseprite={'true' if export.aseprite else 'false'}",
            f"--script-param", f"export_sheet={'true' if export.sheet_png_json else 'false'}",
            f"--script-param", f"export_gif={'true' if export.gif_preview else 'false'}",
            f"--script-param", f"sheet_padding_border={export.sheet_padding_border}",
            f"--script-param", f"sheet_padding_inner={export.sheet_padding_inner}",
            f"--script-param", f"trim={'true' if export.trim else 'false'}",
        ]
        
        return params
    
    async def run_conversion(
        self,
        job: JobSpec,
        profile: ConversionProfile,
    ) -> ConvertResult:
        """Run a conversion job using Aseprite CLI."""
        started_at = datetime.now()
        
        # Create output directory
        output_dir = job.output_dir / job.job_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build command
        lua_script = self.settings.lua_scripts_dir / "convert_sheet_to_anim.lua"
        
        cmd = [
            str(self.settings.aseprite_exe),
            "-b",  # Batch mode (no UI)
        ]
        cmd.extend(self._build_script_params(job, profile, output_dir))
        cmd.extend([
            "--script", str(lua_script),
        ])
        
        try:
            # Run Aseprite
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.settings.workspace_root),
            )
            
            stdout, stderr = await process.communicate()
            
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            
            if process.returncode != 0:
                # Save error log
                error_log_path = output_dir / "aseprite_stderr.txt"
                error_log_path.write_text(stderr.decode("utf-8", errors="replace"))
                
                error_txt_path = output_dir / "error.txt"
                error_txt_path.write_text(
                    f"Aseprite exited with code {process.returncode}\n"
                    f"Command: {' '.join(cmd)}\n"
                )
                
                return ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_message=f"Aseprite exited with code {process.returncode}",
                    error_log_path=error_log_path,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                )
            
            # Parse results from meta.json created by Lua script
            meta_path = output_dir / "meta.json"
            result = await self._parse_results(job, output_dir, meta_path, started_at, completed_at, duration)
            return result
            
        except Exception as e:
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()
            
            # Save error log
            error_txt_path = output_dir / "error.txt"
            error_txt_path.write_text(f"Exception: {str(e)}\n")
            
            return ConvertResult(
                success=False,
                input_path=job.input_path,
                job_name=job.job_name,
                error_message=str(e),
                error_log_path=error_txt_path,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )
    
    async def _parse_results(
        self,
        job: JobSpec,
        output_dir: Path,
        meta_path: Path,
        started_at: datetime,
        completed_at: datetime,
        duration: float,
    ) -> ConvertResult:
        """Parse results from the Lua script output."""
        # Check for expected output files
        aseprite_path = output_dir / "anim.aseprite"
        sheet_png_path = output_dir / "anim_sheet.png"
        sheet_json_path = output_dir / "anim_sheet.json"
        gif_path = output_dir / "anim_preview.gif"
        
        # Read meta.json if it exists
        meta_data: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        
        # Build quality metrics
        quality = None
        if "quality" in meta_data:
            q = meta_data["quality"]
            quality = QualityMetrics(
                anchor_jitter_rms_px=q.get("anchor_jitter_rms_px", 0.0),
                baseline_var_px=q.get("baseline_var_px", 0.0),
                bbox_var=q.get("bbox_var", 0.0),
            )
        
        # Build anchor info
        anchor_info = None
        if "anchor" in meta_data:
            a = meta_data["anchor"]
            anchor_info = AnchorInfo(
                mode=a.get("mode", "unknown"),
                target_x=a.get("target_x", 0),
                target_y=a.get("target_y", 0),
                per_frame_offsets=a.get("per_frame_offsets", []),
            )
        
        return ConvertResult(
            success=True,
            input_path=job.input_path,
            job_name=job.job_name,
            aseprite_path=aseprite_path if aseprite_path.exists() else None,
            sheet_png_path=sheet_png_path if sheet_png_path.exists() else None,
            sheet_json_path=sheet_json_path if sheet_json_path.exists() else None,
            gif_path=gif_path if gif_path.exists() else None,
            meta_path=meta_path if meta_path.exists() else None,
            frame_count=meta_data.get("frame_count", 0),
            grid_rows=meta_data.get("grid", {}).get("rows", 0),
            grid_cols=meta_data.get("grid", {}).get("cols", 0),
            fps=meta_data.get("fps", 0),
            quality=quality,
            anchor_info=anchor_info,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )


def get_runner(settings: Optional[Settings] = None) -> AsepriteRunner:
    """Get an AsepriteRunner instance."""
    return AsepriteRunner(settings)

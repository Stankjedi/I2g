"""
Aseprite CLI runner module.
Handles subprocess execution of Aseprite in batch mode with Lua scripts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import ConversionProfile, ExportConfig, Settings, get_settings
from .detector import detect_grid
from .models import AnchorInfo, ConvertResult, JobSpec, QualityMetrics
from .postprocess import extract_frames_from_sheet, get_post_processor

logger = logging.getLogger(__name__)


def _validate_job_outputs(
    output_dir: Path,
    export: ExportConfig,
    *,
    meta_path: Optional[Path] = None,
) -> tuple[list[str], Optional[str]]:
    missing: list[str] = []

    if export.aseprite and not (output_dir / "anim.aseprite").exists():
        missing.append("anim.aseprite")
    if export.sheet_png_json:
        if not (output_dir / "anim_sheet.png").exists():
            missing.append("anim_sheet.png")
        if not (output_dir / "anim_sheet.json").exists():
            missing.append("anim_sheet.json")
    if export.gif_preview and not (output_dir / "anim_preview.gif").exists():
        missing.append("anim_preview.gif")

    meta_path = meta_path or (output_dir / "meta.json")
    if not meta_path.exists():
        missing.append("meta.json")
        return missing, None

    try:
        json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return missing, f"meta.json invalid JSON: {e}"

    return missing, None


def _interpret_meta_failure(meta: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    status = meta.get("status")
    if not isinstance(status, str):
        return None, None

    normalized = status.strip().lower()
    if normalized not in {"failed", "error"}:
        return None, None

    raw_code = meta.get("error_code")
    raw_message = meta.get("error_message") or meta.get("error")

    code = str(raw_code).strip() if isinstance(raw_code, str) and raw_code.strip() else "LUA_REPORTED_FAILURE"
    message = (
        str(raw_message).strip() if isinstance(raw_message, str) and raw_message.strip() else "Lua conversion failed"
    )

    return code, message


class AsepriteError(Exception):
    """Exception raised when Aseprite execution fails."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "ASEPRITE_ERROR",
        stderr: str = "",
        returncode: int = -1,
    ):
        super().__init__(message)
        self.error_code = error_code
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
            if shutil.which(str(self.settings.aseprite_exe)) is None:
                raise AsepriteError(
                    f"Aseprite executable not found: {self.settings.aseprite_exe}\n"
                    "Set ASEPRITE_EXE environment variable to the correct path.",
                    error_code="ASEPRITE_NOT_FOUND",
                )

    def is_available(self) -> bool:
        """Check if Aseprite is available."""
        try:
            self._validate_aseprite()
            return True
        except AsepriteError:
            return False

    def _build_script_params(self, job: JobSpec, profile: ConversionProfile, output_dir: Path) -> list[str]:
        """Build --script-param arguments for Aseprite CLI."""
        grid = job.grid or profile.grid
        timing = job.timing or profile.timing
        anchor = job.anchor or profile.anchor
        background = job.background or profile.background
        export = job.export or profile.export

        return [
            "--script-param",
            f"input_path={job.input_path}",
            "--script-param",
            f"output_dir={output_dir}",
            "--script-param",
            f"job_name={job.job_name}",
            "--script-param",
            f"grid_rows={grid.rows}",
            "--script-param",
            f"grid_cols={grid.cols}",
            "--script-param",
            f"grid_offset_x={grid.offset_x}",
            "--script-param",
            f"grid_offset_y={grid.offset_y}",
            "--script-param",
            f"grid_pad_x={grid.pad_x}",
            "--script-param",
            f"grid_pad_y={grid.pad_y}",
            "--script-param",
            f"fps={timing.fps}",
            "--script-param",
            f"loop_mode={timing.loop_mode}",
            "--script-param",
            f"anchor_mode={anchor.mode}",
            "--script-param",
            f"anchor_alpha_thresh={anchor.alpha_thresh}",
            "--script-param",
            f"bg_mode={background.mode}",
            "--script-param",
            f"bg_color_r={background.color[0]}",
            "--script-param",
            f"bg_color_g={background.color[1]}",
            "--script-param",
            f"bg_color_b={background.color[2]}",
            "--script-param",
            f"bg_tolerance={background.tolerance}",
            "--script-param",
            f"export_aseprite={'true' if export.aseprite else 'false'}",
            "--script-param",
            f"export_sheet={'true' if export.sheet_png_json else 'false'}",
            "--script-param",
            f"export_gif={'true' if export.gif_preview else 'false'}",
            "--script-param",
            f"sheet_padding_border={export.sheet_padding_border}",
            "--script-param",
            f"sheet_padding_inner={export.sheet_padding_inner}",
            "--script-param",
            f"trim={'true' if export.trim else 'false'}",
        ]

    async def run_conversion(self, job: JobSpec, profile: ConversionProfile) -> ConvertResult:
        """Run a conversion job using Aseprite CLI."""
        started_at = datetime.now()

        output_dir = job.output_dir / job.job_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Auto-detect grid if enabled and the effective grid is the 1x1 default.
        try:
            effective_grid = job.grid or profile.grid
            if job.auto_detect_grid and effective_grid.rows == 1 and effective_grid.cols == 1:
                detection = detect_grid(job.input_path)
                if detection.detected and detection.grid:
                    job.grid = detection.grid
        except Exception:
            logger.exception("Grid auto-detect failed (non-fatal): %s", job.input_path)

        lua_script = self.settings.lua_scripts_dir / "convert_sheet_to_anim.lua"

        cmd: list[str] = [str(self.settings.aseprite_exe), "-b"]
        cmd.extend(self._build_script_params(job, profile, output_dir))
        cmd.extend(["--script", str(lua_script)])

        run_log_path = output_dir / "job.log"

        def write_job_log(data: dict[str, Any]) -> None:
            try:
                run_log_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            except Exception:
                logger.exception("Failed to write job log: %s", run_log_path)

        stdout_log_path: Optional[Path] = None
        stderr_log_path: Optional[Path] = None
        hq_gif_status: dict[str, Any] = {"requested": bool(profile.export.hq_gif), "status": "skipped", "reason": None}

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.settings.workspace_root),
            )

            stdout, stderr = await process.communicate()

            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            if stdout:
                stdout_log_path = output_dir / "aseprite_stdout.txt"
                stdout_log_path.write_text(stdout.decode("utf-8", errors="replace"))
            if stderr:
                stderr_log_path = output_dir / "aseprite_stderr.txt"
                stderr_log_path.write_text(stderr.decode("utf-8", errors="replace"))

            if process.returncode != 0:
                error_txt_path = output_dir / "error.txt"
                error_txt_path.write_text(
                    f"Aseprite exited with code {process.returncode}\nCommand: {cmd}\n",
                    encoding="utf-8",
                )

                write_job_log(
                    {
                        "status": "failed",
                        "error_code": "ASEPRITE_EXIT_NONZERO",
                        "message": f"Aseprite exited with code {process.returncode}",
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "duration_seconds": duration,
                        "cmd": cmd,
                        "returncode": process.returncode,
                        "stdout_log_path": stdout_log_path,
                        "stderr_log_path": stderr_log_path,
                        "error_log_path": stderr_log_path or error_txt_path,
                    }
                )

                return ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_code="ASEPRITE_EXIT_NONZERO",
                    error_message=f"Aseprite exited with code {process.returncode}",
                    error_log_path=stderr_log_path or error_txt_path,
                    stdout_log_path=stdout_log_path,
                    stderr_log_path=stderr_log_path,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                )

            meta_path = output_dir / "meta.json"
            if meta_path.exists():
                meta_data: dict[str, Any] = {}
                try:
                    meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta_data = {}

                meta_error_code, meta_error_message = _interpret_meta_failure(meta_data)
                if meta_error_code and meta_error_message:
                    error_txt_path = output_dir / "error.txt"
                    error_txt_path.write_text(meta_error_message + "\n", encoding="utf-8")

                    write_job_log(
                        {
                            "status": "failed",
                            "error_code": meta_error_code,
                            "message": meta_error_message,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_seconds": duration,
                            "cmd": cmd,
                            "returncode": process.returncode,
                            "stdout_log_path": stdout_log_path,
                            "stderr_log_path": stderr_log_path,
                            "error_log_path": error_txt_path,
                            "meta_path": meta_path,
                            "meta_status": meta_data.get("status"),
                        }
                    )

                    return ConvertResult(
                        success=False,
                        input_path=job.input_path,
                        job_name=job.job_name,
                        error_code=meta_error_code,
                        error_message=meta_error_message,
                        error_log_path=error_txt_path,
                        stdout_log_path=stdout_log_path,
                        stderr_log_path=stderr_log_path,
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_seconds=duration,
                    )

            result = await self._parse_results(job, output_dir, meta_path, started_at, completed_at, duration)
            result.stdout_log_path = stdout_log_path
            result.stderr_log_path = stderr_log_path

            # Optional HQ GIF generation from sheet PNG+JSON.
            if profile.export.hq_gif:
                post = get_post_processor()

                if not post.ffmpeg_available:
                    hq_gif_status["status"] = "skipped"
                    hq_gif_status["reason"] = "ffmpeg_not_available"
                    logger.info("HQ GIF skipped (ffmpeg not available): %s", output_dir)
                elif not result.sheet_png_path or not result.sheet_json_path:
                    hq_gif_status["status"] = "skipped"
                    hq_gif_status["reason"] = "sheet_outputs_missing"
                    logger.info("HQ GIF skipped (sheet outputs missing): %s", output_dir)
                else:
                    frames_dir = output_dir / ".hq_gif_frames"
                    hq_path = output_dir / "anim_preview_hq.gif"
                    target_path = output_dir / "anim_preview.gif"

                    try:
                        frames = extract_frames_from_sheet(result.sheet_png_path, result.sheet_json_path, frames_dir)
                        fps = result.fps or profile.timing.fps
                        ok = await post.create_hq_gif(frames, hq_path, fps=fps)
                        if ok and hq_path.exists():
                            hq_path.replace(target_path)
                            result.gif_path = target_path
                            hq_gif_status["status"] = "success"
                            hq_gif_status["reason"] = None
                            logger.info("HQ GIF generated: %s", target_path)
                        else:
                            hq_gif_status["status"] = "fallback"
                            hq_gif_status["reason"] = "hq_generation_failed"
                            hq_path.unlink(missing_ok=True)
                            logger.warning("HQ GIF generation failed; keeping existing preview: %s", output_dir)
                    except Exception:
                        hq_gif_status["status"] = "fallback"
                        hq_gif_status["reason"] = "exception"
                        hq_path.unlink(missing_ok=True)
                        logger.exception("HQ GIF generation failed; keeping existing preview: %s", output_dir)
                    finally:
                        shutil.rmtree(frames_dir, ignore_errors=True)

            export = job.export or profile.export
            missing_files, meta_error = _validate_job_outputs(
                output_dir,
                export,
                meta_path=meta_path,
            )
            if meta_error:
                missing_files.append("meta.json (invalid JSON)")

            if missing_files or meta_error:
                error_txt_path = output_dir / "error.txt"
                message_parts = []
                if missing_files:
                    message_parts.append(f"missing: {', '.join(missing_files)}")
                if meta_error:
                    message_parts.append(meta_error)
                message = "Output validation failed: " + "; ".join(message_parts)
                error_txt_path.write_text(message + "\n", encoding="utf-8")

                write_job_log(
                    {
                        "status": "failed",
                        "error_code": "OUTPUT_VALIDATION_FAILED",
                        "message": message,
                        "missing_files": missing_files,
                        "meta_error": meta_error,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "duration_seconds": duration,
                        "cmd": cmd,
                        "returncode": process.returncode,
                        "stdout_log_path": stdout_log_path,
                        "stderr_log_path": stderr_log_path,
                        "meta_path": meta_path if meta_path.exists() else None,
                        "hq_gif": hq_gif_status,
                    }
                )

                return ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_code="OUTPUT_VALIDATION_FAILED",
                    error_message=message,
                    error_log_path=error_txt_path,
                    stdout_log_path=stdout_log_path,
                    stderr_log_path=stderr_log_path,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                )

            write_job_log(
                {
                    "status": "success",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_seconds": duration,
                    "cmd": cmd,
                    "returncode": process.returncode,
                    "stdout_log_path": stdout_log_path,
                    "stderr_log_path": stderr_log_path,
                    "meta_path": meta_path if meta_path.exists() else None,
                    "hq_gif": hq_gif_status,
                }
            )

            return result

        except Exception as e:
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            error_txt_path = output_dir / "error.txt"
            error_txt_path.write_text(f"Exception: {str(e)}\n", encoding="utf-8")

            write_job_log(
                {
                    "status": "failed",
                    "error_code": "UNEXPECTED_EXCEPTION",
                    "message": str(e),
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_seconds": duration,
                    "cmd": cmd,
                    "returncode": None,
                    "error_log_path": error_txt_path,
                }
            )

            return ConvertResult(
                success=False,
                input_path=job.input_path,
                job_name=job.job_name,
                error_code="UNEXPECTED_EXCEPTION",
                error_message=str(e),
                error_log_path=error_txt_path,
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
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
        aseprite_path = output_dir / "anim.aseprite"
        sheet_png_path = output_dir / "anim_sheet.png"
        sheet_json_path = output_dir / "anim_sheet.json"
        gif_path = output_dir / "anim_preview.gif"

        meta_data: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        quality = None
        if "quality" in meta_data:
            q = meta_data["quality"]
            quality = QualityMetrics(
                anchor_jitter_rms_px=q.get("anchor_jitter_rms_px", 0.0),
                baseline_var_px=q.get("baseline_var_px", 0.0),
                bbox_var=q.get("bbox_var", 0.0),
            )

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

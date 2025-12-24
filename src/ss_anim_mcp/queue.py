"""
Job queue module with single-worker processing.
Ensures Aseprite is only running one instance at a time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .config import ConversionProfile, Settings, get_settings
from .models import (
    BatchReport,
    ConvertResult,
    JobOverrideError,
    JobSpec,
    apply_job_override,
    apply_tool_overrides,
    load_job_override,
)

logger = logging.getLogger(__name__)


def create_failure_run_dir(failed_root: Path, stem: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = failed_root / stem / timestamp
    counter = 1
    while candidate.exists():
        candidate = failed_root / stem / f"{timestamp}_{counter}"
        counter += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


@dataclass
class QueuedJob:
    """A job waiting in the queue."""

    job: JobSpec
    profile: ConversionProfile
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


class JobQueue:
    """
    Single-worker job queue for Aseprite conversions.
    Processes jobs sequentially to avoid resource conflicts.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        on_job_complete: Optional[Callable[[ConvertResult], Awaitable[None]]] = None,
    ):
        self.settings = settings or get_settings()
        self.on_job_complete = on_job_complete

        self._queue: asyncio.Queue[QueuedJob] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

        # Statistics
        self._total_processed = 0
        self._total_success = 0
        self._total_failed = 0
        self._last_error: Optional[str] = None
        self._current_job: Optional[QueuedJob] = None
        self._current_job_started_at: Optional[datetime] = None

    @property
    def queue_length(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def recent_success(self) -> int:
        return self._total_success

    @property
    def recent_failures(self) -> int:
        return self._total_failed

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def current_job(self) -> Optional[dict[str, object]]:
        if self._current_job is None:
            return None
        job = self._current_job.job
        return {
            "job_name": job.job_name,
            "input_path": str(job.input_path),
            "profile": self._current_job.profile.name,
            "queued_at": self._current_job.created_at,
            "started_at": self._current_job_started_at,
        }

    async def start(self) -> None:
        """Start the job queue worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop the job queue worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def enqueue(self, job: JobSpec, profile: ConversionProfile) -> None:
        """Add a job to the queue."""
        await self._queue.put(QueuedJob(job=job, profile=profile))

    async def _worker_loop(self) -> None:
        """Main worker loop - processes jobs one at a time."""
        # Import here to avoid circular dependency
        from .aseprite_runner import AsepriteError, AsepriteRunner

        while self._running:
            try:
                # Wait for a job with timeout (allows checking _running flag)
                try:
                    queued = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self._current_job = queued
                self._current_job_started_at = datetime.now()

                try:
                    logger.info(
                        "Job start: job_name=%s profile=%s input=%s",
                        queued.job.job_name,
                        queued.profile.name,
                        queued.job.input_path,
                    )

                    runner = AsepriteRunner(self.settings)
                    result = await runner.run_conversion(queued.job, queued.profile)

                except AsepriteError as e:
                    completed_at = datetime.now()
                    started_at = self._current_job_started_at or completed_at
                    duration = (completed_at - started_at).total_seconds()

                    job_output_dir = queued.job.output_dir / queued.job.job_name
                    job_output_dir.mkdir(parents=True, exist_ok=True)

                    error_txt_path = job_output_dir / "error.txt"
                    error_txt_path.write_text(str(e) + "\n", encoding="utf-8")

                    run_log_path = job_output_dir / "job.log"
                    run_log_path.write_text(
                        json.dumps(
                            {
                                "status": "failed",
                                "error_code": e.error_code,
                                "message": str(e),
                                "started_at": started_at,
                                "completed_at": completed_at,
                                "duration_seconds": duration,
                            },
                            indent=2,
                            default=str,
                        ),
                        encoding="utf-8",
                    )

                    result = ConvertResult(
                        success=False,
                        input_path=queued.job.input_path,
                        job_name=queued.job.job_name,
                        error_code=e.error_code,
                        error_message=str(e),
                        error_log_path=error_txt_path,
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_seconds=duration,
                    )

                except Exception as e:
                    completed_at = datetime.now()
                    started_at = self._current_job_started_at or completed_at
                    duration = (completed_at - started_at).total_seconds()

                    job_output_dir = queued.job.output_dir / queued.job.job_name
                    job_output_dir.mkdir(parents=True, exist_ok=True)

                    error_txt_path = job_output_dir / "error.txt"
                    error_txt_path.write_text(f"Exception: {str(e)}\n", encoding="utf-8")

                    run_log_path = job_output_dir / "job.log"
                    run_log_path.write_text(
                        json.dumps(
                            {
                                "status": "failed",
                                "error_code": "UNEXPECTED_EXCEPTION",
                                "message": str(e),
                                "started_at": started_at,
                                "completed_at": completed_at,
                                "duration_seconds": duration,
                            },
                            indent=2,
                            default=str,
                        ),
                        encoding="utf-8",
                    )

                    logger.exception(
                        "Job failed unexpectedly: job_name=%s input=%s",
                        queued.job.job_name,
                        queued.job.input_path,
                    )

                    result = ConvertResult(
                        success=False,
                        input_path=queued.job.input_path,
                        job_name=queued.job.job_name,
                        error_code="UNEXPECTED_EXCEPTION",
                        error_message=str(e),
                        error_log_path=error_txt_path,
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_seconds=duration,
                    )

                # Update stats
                self._total_processed += 1
                if result.success:
                    self._total_success += 1
                    await self._move_to_processed(
                        queued.job.input_path,
                        processed_dir=queued.job.processed_dir,
                    )
                else:
                    self._total_failed += 1
                    self._last_error = result.error_message
                    _, failed_log = await self._move_to_failed(
                        queued.job.input_path,
                        result.error_message,
                        failed_dir=queued.job.failed_dir,
                    )
                    if failed_log:
                        result.error_log_path = failed_log

                logger.info(
                    "Job end: job_name=%s success=%s error_code=%s",
                    queued.job.job_name,
                    result.success,
                    result.error_code,
                )

                if self.on_job_complete:
                    await self.on_job_complete(result)

                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Queue worker loop error")
            finally:
                self._current_job = None
                self._current_job_started_at = None

    async def _move_to_processed(self, input_path: Path, processed_dir: Optional[Path] = None) -> None:
        """Move input file to processed folder."""
        if not input_path.exists():
            return

        target_root = processed_dir or self.settings.processed_dir
        dest = target_root / input_path.name
        counter = 1
        while dest.exists():
            dest = target_root / f"{input_path.stem}_{counter}{input_path.suffix}"
            counter += 1

        shutil.move(str(input_path), str(dest))

    async def _move_to_failed(
        self,
        input_path: Path,
        error_message: Optional[str],
        failed_dir: Optional[Path] = None,
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Move input file to failed folder with error log."""
        if not input_path.exists():
            return None, None

        target_root = failed_dir or self.settings.failed_dir
        fail_dir = create_failure_run_dir(target_root, input_path.stem)

        dest = fail_dir / input_path.name
        counter = 1
        while dest.exists():
            dest = fail_dir / f"{input_path.stem}_{counter}{input_path.suffix}"
            counter += 1
        shutil.move(str(input_path), str(dest))

        error_log_path = None
        if error_message:
            error_log_path = fail_dir / "error.txt"
            error_log_path.write_text(f"Error: {error_message}\n", encoding="utf-8")

        return fail_dir, error_log_path

    async def process_batch(
        self,
        files: list[Path],
        profile: ConversionProfile,
        output_dir: Optional[Path] = None,
        *,
        grid_rows: Optional[int] = None,
        grid_cols: Optional[int] = None,
        fps: Optional[int] = None,
        processed_dir: Optional[Path] = None,
        failed_dir: Optional[Path] = None,
    ) -> BatchReport:
        """
        Process a batch of files synchronously (not using queue).
        Returns when all files are processed.
        """
        from .aseprite_runner import AsepriteError, AsepriteRunner

        report = BatchReport(total_files=len(files))
        out_dir = output_dir or self.settings.out_dir

        for file_path in files:
            effective_profile = profile.model_copy(deep=True)
            job = JobSpec.from_file(file_path, out_dir)

            try:
                override = load_job_override(file_path)
                if override is not None:
                    apply_job_override(effective_profile, override)
                    if override.auto_detect_grid is not None:
                        job.auto_detect_grid = override.auto_detect_grid
            except JobOverrideError as e:
                job_output_dir = job.output_dir / job.job_name
                job_output_dir.mkdir(parents=True, exist_ok=True)
                error_txt_path = job_output_dir / "error.txt"
                error_txt_path.write_text(str(e) + "\n", encoding="utf-8")
                result = ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_code=e.error_code,
                    error_message=str(e),
                    error_log_path=error_txt_path,
                )
                report.add_result(result)
                _, failed_log = await self._move_to_failed(file_path, result.error_message, failed_dir=failed_dir)
                if failed_log:
                    result.error_log_path = failed_log
                continue

            apply_tool_overrides(
                effective_profile,
                grid_rows=grid_rows,
                grid_cols=grid_cols,
                fps=fps,
            )

            try:
                runner = AsepriteRunner(self.settings)
                result = await runner.run_conversion(job, effective_profile)
            except AsepriteError as e:
                job_output_dir = job.output_dir / job.job_name
                job_output_dir.mkdir(parents=True, exist_ok=True)
                error_txt_path = job_output_dir / "error.txt"
                error_txt_path.write_text(str(e) + "\n", encoding="utf-8")
                result = ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_code=e.error_code,
                    error_message=str(e),
                    error_log_path=error_txt_path,
                )
            except Exception as e:
                job_output_dir = job.output_dir / job.job_name
                job_output_dir.mkdir(parents=True, exist_ok=True)
                error_txt_path = job_output_dir / "error.txt"
                error_txt_path.write_text(f"Exception: {str(e)}\n", encoding="utf-8")
                result = ConvertResult(
                    success=False,
                    input_path=job.input_path,
                    job_name=job.job_name,
                    error_code="UNEXPECTED_EXCEPTION",
                    error_message=str(e),
                    error_log_path=error_txt_path,
                )

            report.add_result(result)

            if result.success:
                await self._move_to_processed(file_path, processed_dir=processed_dir)
            else:
                _, failed_log = await self._move_to_failed(file_path, result.error_message, failed_dir=failed_dir)
                if failed_log:
                    result.error_log_path = failed_log

        report.completed_at = datetime.now()
        return report

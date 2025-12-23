"""
Job queue module with single-worker processing.
Ensures Aseprite is only running one instance at a time.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass

from .config import Settings, get_settings, ConversionProfile
from .models import JobSpec, ConvertResult, BatchReport


@dataclass
class QueuedJob:
    """A job waiting in the queue."""
    job: JobSpec
    profile: ConversionProfile
    created_at: datetime = None
    
    def __post_init__(self):
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
        from .aseprite_runner import AsepriteRunner
        
        runner = AsepriteRunner(self.settings)
        
        while self._running:
            try:
                # Wait for a job with timeout (allows checking _running flag)
                try:
                    queued = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                self._current_job = queued
                
                try:
                    # Run the conversion
                    result = await runner.run_conversion(queued.job, queued.profile)
                    
                    # Update stats
                    self._total_processed += 1
                    if result.success:
                        self._total_success += 1
                        # Move original to processed
                        await self._move_to_processed(queued.job.input_path)
                    else:
                        self._total_failed += 1
                        self._last_error = result.error_message
                        # Move original to failed
                        await self._move_to_failed(queued.job.input_path, result.error_message)
                    
                    # Notify callback
                    if self.on_job_complete:
                        await self.on_job_complete(result)
                
                finally:
                    self._current_job = None
                    self._queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = str(e)
                self._total_failed += 1
    
    async def _move_to_processed(self, input_path: Path) -> None:
        """Move input file to processed folder."""
        if not input_path.exists():
            return
        
        dest = self.settings.processed_dir / input_path.name
        # Handle name conflicts
        counter = 1
        while dest.exists():
            dest = self.settings.processed_dir / f"{input_path.stem}_{counter}{input_path.suffix}"
            counter += 1
        
        shutil.move(str(input_path), str(dest))
    
    async def _move_to_failed(self, input_path: Path, error_message: Optional[str]) -> None:
        """Move input file to failed folder with error log."""
        if not input_path.exists():
            return
        
        # Create subfolder for this failure
        fail_dir = self.settings.failed_dir / input_path.stem
        fail_dir.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        dest = fail_dir / input_path.name
        shutil.move(str(input_path), str(dest))
        
        # Write error log
        if error_message:
            error_log = fail_dir / "error.txt"
            error_log.write_text(f"Error: {error_message}\n")
    
    async def process_batch(
        self,
        files: list[Path],
        profile: ConversionProfile,
        output_dir: Optional[Path] = None,
    ) -> BatchReport:
        """
        Process a batch of files synchronously (not using queue).
        Returns when all files are processed.
        """
        from .aseprite_runner import AsepriteRunner
        
        report = BatchReport(total_files=len(files))
        runner = AsepriteRunner(self.settings)
        out_dir = output_dir or self.settings.out_dir
        
        for file_path in files:
            job = JobSpec.from_file(file_path, out_dir)
            result = await runner.run_conversion(job, profile)
            report.add_result(result)
            
            # Move file based on result
            if result.success:
                await self._move_to_processed(file_path)
            else:
                await self._move_to_failed(file_path, result.error_message)
        
        report.completed_at = datetime.now()
        return report

"""
Folder watcher module with stable write detection.
Uses watchfiles (primary) with a polling fallback for file system monitoring.
"""

from __future__ import annotations

import asyncio
import time
import logging
from pathlib import Path
from typing import Callable, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class StableWriteGuard:
    """
    Ensures files are completely written before processing.
    Checks file size/mtime stability over multiple intervals.
    """
    
    def __init__(
        self,
        check_count: int = 3,
        check_interval_ms: int = 300,
    ):
        self.check_count = check_count
        self.check_interval_ms = check_interval_ms
        self._pending: dict[Path, tuple[int, float, int]] = {}  # path -> (size, mtime, stable_count)
    
    async def wait_for_stable(self, path: Path, timeout_seconds: float = 30.0) -> bool:
        """
        Wait for a file to become stable (fully written).
        Returns True if stable, False if timeout or file disappeared.
        """
        start_time = time.time()
        last_size = -1
        last_mtime = -1.0
        stable_count = 0
        
        while time.time() - start_time < timeout_seconds:
            if not path.exists():
                return False
            
            try:
                stat = path.stat()
                current_size = stat.st_size
                current_mtime = stat.st_mtime
            except OSError:
                return False
            
            if current_size == last_size and current_mtime == last_mtime:
                stable_count += 1
                if stable_count >= self.check_count:
                    return True
            else:
                stable_count = 0
                last_size = current_size
                last_mtime = current_mtime
            
            await asyncio.sleep(self.check_interval_ms / 1000.0)
        
        return False


class FolderWatcher:
    """
    Watches a folder for new files and invokes callbacks.
    Implements stable write detection to avoid processing incomplete files.
    """
    
    def __init__(
        self,
        inbox_dir: Path,
        on_new_file: Callable[[Path], None],
        extensions: Optional[Set[str]] = None,
    ):
        self.inbox_dir = inbox_dir
        self.on_new_file = on_new_file
        self.extensions = extensions or {".png", ".jpg", ".jpeg"}
        self.stable_guard = StableWriteGuard()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_files: Set[Path] = set()
        self._files_processed_count = 0
        self._last_activity: Optional[datetime] = None
        self.poll_interval_seconds = 1.0
        self._error_count = 0
        self._last_error: Optional[str] = None
        self._last_scan_at: Optional[datetime] = None
        self._prune_threshold = 10_000

    def _prune_state(self, current_files: Set[Path], seen_files: dict[Path, float]) -> None:
        """Prune internal state to prevent unbounded growth in long-running watch mode."""
        if self._processed_files:
            self._processed_files.intersection_update(current_files)

        for path in list(seen_files.keys()):
            if path not in current_files:
                seen_files.pop(path, None)

    def _prune_processed_files_nonexistent(self) -> None:
        if not self._processed_files:
            return
        self._processed_files = {path for path in self._processed_files if path.exists()}
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def files_processed(self) -> int:
        return self._files_processed_count
    
    @property
    def last_activity(self) -> Optional[datetime]:
        return self._last_activity

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def last_scan_at(self) -> Optional[datetime]:
        return self._last_scan_at
    
    def _is_valid_file(self, path: Path) -> bool:
        """Check if file should be processed."""
        if not path.is_file():
            return False
        if path.name.startswith("."):
            return False
        if path.suffix.lower() not in self.extensions:
            return False
        return True
    
    async def _watch_loop_watchfiles(self) -> None:
        """Watch loop using watchfiles library."""
        try:
            import watchfiles
            
            async for changes in watchfiles.awatch(self.inbox_dir):
                if not self._running:
                    break
                
                for change_type, file_path in changes:
                    path = Path(file_path)
                    
                    # Only process new/modified files
                    if change_type in (watchfiles.Change.added, watchfiles.Change.modified):
                        if self._is_valid_file(path) and path not in self._processed_files:
                            # Wait for stable write
                            if await self.stable_guard.wait_for_stable(path):
                                self._processed_files.add(path)
                                if len(self._processed_files) > self._prune_threshold:
                                    self._prune_processed_files_nonexistent()
                                self._files_processed_count += 1
                                self._last_activity = datetime.now()
                                self.on_new_file(path)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            logger.exception("watchfiles loop error: inbox=%s", self.inbox_dir)
            await asyncio.sleep(1.0)
    
    async def _watch_loop_polling(self) -> None:
        """Fallback polling-based watch loop."""
        seen_files: dict[Path, float] = {}
        poll_interval = self.poll_interval_seconds
        
        while self._running:
            try:
                # Scan directory
                self._last_scan_at = datetime.now()
                current_files = {
                    p for p in self.inbox_dir.iterdir()
                    if self._is_valid_file(p)
                }

                self._prune_state(current_files, seen_files)
                
                for path in current_files:
                    if path in self._processed_files:
                        continue
                    
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    
                    if path not in seen_files:
                        seen_files[path] = mtime
                    elif mtime == seen_files[path]:
                        # File hasn't changed, check if stable
                        if await self.stable_guard.wait_for_stable(path, timeout_seconds=5.0):
                            self._processed_files.add(path)
                            self._files_processed_count += 1
                            self._last_activity = datetime.now()
                            self.on_new_file(path)
                    else:
                        seen_files[path] = mtime
                
                await asyncio.sleep(poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                logger.exception("polling watch loop error: inbox=%s", self.inbox_dir)
                await asyncio.sleep(min(poll_interval * 2, 5.0))
    
    async def start(self) -> None:
        """Start watching the folder."""
        if self._running:
            return
        
        self._running = True
        
        # Try watchfiles first, fall back to polling
        try:
            import watchfiles  # noqa: F401
            self._task = asyncio.create_task(self._watch_loop_watchfiles())
        except ImportError:
            self._task = asyncio.create_task(self._watch_loop_polling())
    
    async def stop(self) -> None:
        """Stop watching the folder."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
    
    def get_existing_files(self) -> list[Path]:
        """Get list of unprocessed files currently in inbox."""
        files = []
        for path in self.inbox_dir.iterdir():
            if self._is_valid_file(path) and path not in self._processed_files:
                files.append(path)
        return sorted(files, key=lambda p: p.stat().st_mtime)
    
    def mark_processed(self, path: Path) -> None:
        """Mark a file as processed (won't be triggered again)."""
        self._processed_files.add(path)

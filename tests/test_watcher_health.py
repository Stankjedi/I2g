from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ss_anim_mcp.watcher import FolderWatcher


@pytest.mark.asyncio
async def test_watcher_polling_error_updates_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    watcher = FolderWatcher(tmp_path, lambda _: None)
    watcher.poll_interval_seconds = 0.01

    def boom(self) -> list[Path]:
        raise RuntimeError("boom")

    monkeypatch.setattr(Path, "iterdir", boom, raising=True)

    watcher._running = True
    task = asyncio.create_task(watcher._watch_loop_polling())
    await asyncio.sleep(0.05)
    watcher._running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert watcher.error_count >= 1
    assert watcher.last_error is not None
    assert "boom" in watcher.last_error

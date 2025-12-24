from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.queue import JobQueue


@pytest.mark.asyncio
async def test_failure_retention_creates_unique_runs(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    file1 = input_dir / "sprite.png"
    file1.write_bytes(b"one")
    run_dir1, log1 = await queue._move_to_failed(file1, "boom", failed_dir=settings.failed_dir)

    file2 = input_dir / "sprite.png"
    file2.write_bytes(b"two")
    run_dir2, log2 = await queue._move_to_failed(file2, "boom2", failed_dir=settings.failed_dir)

    assert run_dir1 is not None
    assert run_dir2 is not None
    assert run_dir1 != run_dir2
    assert log1 is not None and log1.exists()
    assert log2 is not None and log2.exists()

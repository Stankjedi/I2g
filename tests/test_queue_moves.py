from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.queue import JobQueue


@pytest.mark.asyncio
async def test_move_to_processed_name_collision(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    settings = Settings.from_env(workspace_override=workspace)
    settings.ensure_directories()

    queue = JobQueue(settings=settings)

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    # Create an existing file in processed to force a name collision.
    existing = settings.processed_dir / "sprite.png"
    existing.write_bytes(b"old")

    input_file = input_dir / "sprite.png"
    input_file.write_bytes(b"new")

    await queue._move_to_processed(input_file)

    assert not input_file.exists()
    assert existing.exists()

    moved = settings.processed_dir / "sprite_1.png"
    assert moved.exists()
    assert moved.read_bytes() == b"new"


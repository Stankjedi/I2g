from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.queue import JobQueue
from ss_anim_mcp.server import WorkspaceContext, tool_convert_inbox


@pytest.mark.asyncio
async def test_convert_inbox_rejects_external_processed_dir(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)

    external_dir = tmp_path / "external"
    external_dir.mkdir(parents=True, exist_ok=True)

    context = WorkspaceContext(settings=settings, queue=queue)
    result = await tool_convert_inbox(context, {"processed_dir": str(external_dir)})

    assert result.get("error_code") == "PATH_OUTSIDE_WORKSPACE"


@pytest.mark.asyncio
async def test_move_to_processed_uses_override(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)

    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_file = input_dir / "sprite.png"
    input_file.write_bytes(b"data")

    custom_processed = settings.workspace_root / "custom_processed"
    custom_processed.mkdir(parents=True, exist_ok=True)

    await queue._move_to_processed(input_file, processed_dir=custom_processed)

    assert not input_file.exists()
    assert (custom_processed / "sprite.png").exists()

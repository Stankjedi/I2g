from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.queue import JobQueue
from ss_anim_mcp.server import WorkspaceContext, tool_convert_file, tool_watch_start


@pytest.mark.asyncio
async def test_convert_file_rejects_external_input_path(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)
    context = WorkspaceContext(settings=settings, queue=queue)

    external = tmp_path / "external" / "sprite.png"
    result = await tool_convert_file(context, {"input_path": str(external)})

    assert result.get("error_code") == "PATH_OUTSIDE_WORKSPACE"
    assert result.get("field") == "input_path"


@pytest.mark.asyncio
async def test_convert_file_allows_external_input_path_when_opted_in(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)
    context = WorkspaceContext(settings=settings, queue=queue)

    external = tmp_path / "external" / "sprite.png"
    result = await tool_convert_file(context, {"input_path": str(external), "allow_external_paths": True})

    assert result.get("error_code") == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_watch_start_rejects_external_inbox_dir(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)
    context = WorkspaceContext(settings=settings, queue=queue)

    external_inbox = tmp_path / "external_inbox"
    result = await tool_watch_start(context, {"inbox_dir": str(external_inbox)})

    assert result.get("error_code") == "PATH_OUTSIDE_WORKSPACE"
    assert result.get("field") == "inbox_dir"


@pytest.mark.asyncio
async def test_watch_start_rejects_external_out_dir(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()
    queue = JobQueue(settings=settings)
    context = WorkspaceContext(settings=settings, queue=queue)

    inbox_inside = settings.workspace_root / "custom_inbox"
    external_out = tmp_path / "external_out"
    result = await tool_watch_start(context, {"inbox_dir": str(inbox_inside), "out_dir": str(external_out)})

    assert result.get("error_code") == "PATH_OUTSIDE_WORKSPACE"
    assert result.get("field") == "out_dir"


from __future__ import annotations

from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.queue import JobQueue
from ss_anim_mcp.server import WorkspaceContext, tool_doctor


@pytest.mark.asyncio
async def test_doctor_returns_shape(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    context = WorkspaceContext(settings=settings, queue=JobQueue(settings))
    result = await tool_doctor(context)

    assert result["status"] in ("ok", "warning")
    assert "version" in result
    assert "python" in result
    assert "aseprite" in result
    assert "workspace" in result
    assert "dependencies" in result
    assert isinstance(result.get("findings"), list)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ss_anim_mcp.config import Settings
from ss_anim_mcp.models import apply_job_override, apply_tool_overrides, load_job_override
from ss_anim_mcp.queue import JobQueue
from ss_anim_mcp.server import WorkspaceContext, tool_convert_file


def test_job_override_applies_and_tool_overrides_win(tmp_path: Path) -> None:
    input_path = tmp_path / "walk.png"
    input_path.write_bytes(b"")

    override_path = tmp_path / "walk.job.json"
    override_path.write_text(
        json.dumps(
            {
                "grid": {"rows": 3, "cols": 4},
                "timing": {"fps": 8, "loop_mode": "loop"},
                "auto_detect_grid": False,
            }
        ),
        encoding="utf-8",
    )

    override = load_job_override(input_path)
    assert override is not None
    assert override.auto_detect_grid is False

    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    profile = settings.get_profile("game_default")

    apply_job_override(profile, override)
    apply_tool_overrides(profile, grid_rows=2, fps=12)

    assert profile.grid.rows == 2  # tool overrides win
    assert profile.grid.cols == 4  # override applied
    assert profile.timing.fps == 12


@pytest.mark.asyncio
async def test_invalid_job_override_returns_structured_error(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path / "ws")
    settings.ensure_directories()

    input_path = settings.workspace_root / "walk.png"
    input_path.write_bytes(b"")

    (settings.workspace_root / "walk.job.json").write_text("{ invalid", encoding="utf-8")

    context = WorkspaceContext(settings=settings, queue=JobQueue(settings))
    result = await tool_convert_file(context, {"input_path": str(input_path), "profile": "game_default"})

    assert result.get("error_code") == "JOB_OVERRIDE_INVALID"
    assert "override" in (result.get("message") or "").lower()

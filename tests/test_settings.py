from __future__ import annotations

from pathlib import Path

from ss_anim_mcp.config import Settings


def test_settings_from_env_workspace_override(tmp_path: Path) -> None:
    settings = Settings.from_env(workspace_override=tmp_path)
    assert settings.workspace_root == tmp_path.resolve()
    assert settings.inbox_dir == settings.workspace_root / "inbox"
    assert settings.out_dir == settings.workspace_root / "out"
    assert settings.processed_dir == settings.workspace_root / "processed"
    assert settings.failed_dir == settings.workspace_root / "failed"


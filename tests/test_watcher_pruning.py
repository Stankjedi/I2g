from __future__ import annotations

from pathlib import Path

from ss_anim_mcp.watcher import FolderWatcher


def test_prune_state_removes_stale_processed_and_seen_entries(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path, lambda _: None)

    current = {tmp_path / "a.png", tmp_path / "b.png"}
    seen_files = {tmp_path / "a.png": 1.0, tmp_path / "c.png": 2.0}
    watcher._processed_files = {tmp_path / "a.png", tmp_path / "c.png", tmp_path / "d.png"}

    watcher._prune_state(current, seen_files)

    assert watcher._processed_files == {tmp_path / "a.png"}
    assert set(seen_files.keys()) == {tmp_path / "a.png"}


def test_prune_processed_files_nonexistent_keeps_only_existing_paths(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path, lambda _: None)

    existing = tmp_path / "exists.png"
    existing.write_bytes(b"x")
    missing = tmp_path / "missing.png"

    watcher._processed_files = {existing, missing}
    watcher._prune_processed_files_nonexistent()

    assert watcher._processed_files == {existing}


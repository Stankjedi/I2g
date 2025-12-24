from __future__ import annotations

import os
from pathlib import Path

from ss_anim_mcp.server import list_inbox_files


def test_list_inbox_files_order_and_limit(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    file_a = inbox / "a.png"
    file_b = inbox / "b.png"
    file_c = inbox / "c.jpg"
    file_txt = inbox / "note.txt"

    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")
    file_c.write_bytes(b"c")
    file_txt.write_bytes(b"x")

    os.utime(file_a, (100, 100))
    os.utime(file_b, (100, 100))
    os.utime(file_c, (200, 200))

    files = list_inbox_files(inbox, limit=2, exts=(".png", ".jpg", ".jpeg"))
    assert [p.name for p in files] == ["a.png", "b.png"]

    files_all = list_inbox_files(inbox, limit=10, exts=(".png", ".jpg", ".jpeg"))
    assert [p.name for p in files_all] == ["a.png", "b.png", "c.jpg"]

from __future__ import annotations

import os
from pathlib import Path


def test_repository_text_files_are_lf_only() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    include_exts = {".py", ".md", ".lua", ".json", ".yml", ".yaml", ".toml", ".txt"}
    exclude_dirs = {".git", "__pycache__", ".pytest_cache", "workspace", ".vscode"}

    offenders: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.name in {".gitignore", ".gitattributes"} or path.suffix.lower() in include_exts:
                data = path.read_bytes()
                if b"\r" in data:
                    offenders.append(str(path.relative_to(repo_root)))

    assert offenders == [], "CRLF/CR characters found in:\n" + "\n".join(offenders)


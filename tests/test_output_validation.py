from __future__ import annotations

import json
from pathlib import Path

from ss_anim_mcp.aseprite_runner import _validate_job_outputs
from ss_anim_mcp.config import ExportConfig


def _write_dummy(path: Path) -> None:
    path.write_bytes(b"x")


def test_output_validation_missing_meta(tmp_path: Path) -> None:
    output_dir = tmp_path / "job"
    output_dir.mkdir(parents=True)

    _write_dummy(output_dir / "anim.aseprite")
    _write_dummy(output_dir / "anim_sheet.png")
    _write_dummy(output_dir / "anim_sheet.json")
    _write_dummy(output_dir / "anim_preview.gif")

    export = ExportConfig()
    missing, meta_error = _validate_job_outputs(output_dir, export)

    assert "meta.json" in missing
    assert meta_error is None


def test_output_validation_invalid_meta(tmp_path: Path) -> None:
    output_dir = tmp_path / "job"
    output_dir.mkdir(parents=True)

    _write_dummy(output_dir / "anim.aseprite")
    _write_dummy(output_dir / "anim_sheet.png")
    _write_dummy(output_dir / "anim_sheet.json")
    _write_dummy(output_dir / "anim_preview.gif")
    (output_dir / "meta.json").write_text("{ invalid", encoding="utf-8")

    export = ExportConfig()
    missing, meta_error = _validate_job_outputs(output_dir, export)

    assert missing == []
    assert meta_error is not None


def test_output_validation_missing_sheet_json(tmp_path: Path) -> None:
    output_dir = tmp_path / "job"
    output_dir.mkdir(parents=True)

    _write_dummy(output_dir / "anim.aseprite")
    _write_dummy(output_dir / "anim_sheet.png")
    _write_dummy(output_dir / "anim_preview.gif")
    (output_dir / "meta.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    export = ExportConfig()
    missing, meta_error = _validate_job_outputs(output_dir, export)

    assert "anim_sheet.json" in missing
    assert meta_error is None


def test_output_validation_success(tmp_path: Path) -> None:
    output_dir = tmp_path / "job"
    output_dir.mkdir(parents=True)

    _write_dummy(output_dir / "anim.aseprite")
    _write_dummy(output_dir / "anim_sheet.png")
    _write_dummy(output_dir / "anim_sheet.json")
    _write_dummy(output_dir / "anim_preview.gif")
    (output_dir / "meta.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    export = ExportConfig()
    missing, meta_error = _validate_job_outputs(output_dir, export)

    assert missing == []
    assert meta_error is None

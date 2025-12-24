from __future__ import annotations

import json

from ss_anim_mcp.aseprite_runner import _interpret_meta_failure


def test_interpret_meta_failure_success_is_none() -> None:
    meta_json = json.dumps(
        {
            "status": "success",
            "error_code": "",
            "error_message": "",
            "job_name": "walk",
        }
    )
    meta = json.loads(meta_json)
    code, message = _interpret_meta_failure(meta)
    assert code is None
    assert message is None


def test_interpret_meta_failure_failed_surfaces_code_and_message() -> None:
    meta_json = json.dumps(
        {
            "status": "failed",
            "error_code": "INPUT_NOT_FOUND",
            "error_message": "Input file not found: /tmp/foo.png",
            "params": {"input_path": "/tmp/foo.png"},
        }
    )
    meta = json.loads(meta_json)
    code, message = _interpret_meta_failure(meta)
    assert code == "INPUT_NOT_FOUND"
    assert "Input file not found" in (message or "")


def test_interpret_meta_failure_failed_defaults_when_fields_missing() -> None:
    meta_json = json.dumps({"status": "failed"})
    meta = json.loads(meta_json)
    code, message = _interpret_meta_failure(meta)
    assert code == "LUA_REPORTED_FAILURE"
    assert message == "Lua conversion failed"


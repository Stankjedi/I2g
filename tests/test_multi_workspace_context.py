from __future__ import annotations

import json
from pathlib import Path

import pytest

from ss_anim_mcp import server as server_mod


def test_contexts_are_isolated(tmp_path: Path) -> None:
    server_mod._contexts.clear()

    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"

    ctx1 = server_mod._get_context(ws1)
    ctx2 = server_mod._get_context(ws2)

    assert ctx1 is not ctx2
    assert ctx1.queue is not ctx2.queue
    assert ctx1.settings.workspace_root == ws1.resolve()
    assert ctx2.settings.workspace_root == ws2.resolve()


@pytest.mark.asyncio
async def test_status_uses_workspace_root(tmp_path: Path) -> None:
    server_mod._contexts.clear()

    ws = tmp_path / "workspace"
    result = await server_mod.call_tool("status", {"workspace_root": str(ws)})
    payload = json.loads(result[0].text)

    assert payload["workspace"]["root"] == str(ws.resolve())

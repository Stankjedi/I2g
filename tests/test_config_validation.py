from __future__ import annotations

import pytest
from pydantic import ValidationError

from ss_anim_mcp.config import AnchorConfig, BackgroundConfig, TimingConfig


def test_mode_normalization() -> None:
    assert TimingConfig(loop_mode="PINGPONG").loop_mode == "pingpong"
    assert AnchorConfig(mode="FOOT").mode == "foot"
    assert BackgroundConfig(mode="Transparent").mode == "transparent"


def test_invalid_modes_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        TimingConfig(loop_mode="nope")
    assert "loop_mode" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        AnchorConfig(mode="bad")
    assert "mode" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        BackgroundConfig(mode="bad")
    assert "mode" in str(exc.value)


"""
Configuration module for ss_anim_mcp server.
Handles environment variables, paths, and conversion profiles.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class GridConfig(BaseModel):
    """Grid configuration for spritesheet splitting."""
    rows: int = Field(default=1, ge=1, description="Number of rows in the grid")
    cols: int = Field(default=1, ge=1, description="Number of columns in the grid")
    offset_x: int = Field(default=0, ge=0, description="X offset from top-left")
    offset_y: int = Field(default=0, ge=0, description="Y offset from top-left")
    pad_x: int = Field(default=0, ge=0, description="Horizontal padding between frames")
    pad_y: int = Field(default=0, ge=0, description="Vertical padding between frames")


class TimingConfig(BaseModel):
    """Timing configuration for animation."""
    fps: int = Field(default=12, ge=1, le=120, description="Frames per second")
    loop_mode: str = Field(default="loop", description="Loop mode: 'loop' or 'pingpong'")


class AnchorConfig(BaseModel):
    """Anchor/pivot configuration for frame alignment."""
    mode: str = Field(default="foot", description="Anchor mode: 'foot', 'center', 'none'")
    alpha_thresh: int = Field(default=10, ge=0, le=255, description="Alpha threshold for opaque detection")
    x_band: tuple[float, float] = Field(default=(0.25, 0.75), description="X band for anchor detection")


class BackgroundConfig(BaseModel):
    """Background processing configuration."""
    mode: str = Field(default="transparent", description="Mode: 'transparent', 'keep', 'color'")
    color: tuple[int, int, int] = Field(default=(255, 255, 255), description="Background color RGB")
    tolerance: int = Field(default=8, ge=0, le=255, description="Color match tolerance")


class ExportConfig(BaseModel):
    """Export configuration."""
    aseprite: bool = Field(default=True, description="Export .aseprite file")
    sheet_png_json: bool = Field(default=True, description="Export sheet PNG + JSON")
    gif_preview: bool = Field(default=True, description="Export GIF preview")
    sheet_padding_border: int = Field(default=2, ge=0, description="Sheet border padding")
    sheet_padding_inner: int = Field(default=2, ge=0, description="Sheet inner padding")
    trim: bool = Field(default=False, description="Trim transparent pixels")
    hq_gif: bool = Field(default=False, description="Use FFmpeg for HQ GIF")


class ConversionProfile(BaseModel):
    """Complete conversion profile combining all configs."""
    name: str = Field(default="default", description="Profile name")
    grid: GridConfig = Field(default_factory=GridConfig)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    anchor: AnchorConfig = Field(default_factory=AnchorConfig)
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)


# Predefined profiles
PROFILES: dict[str, ConversionProfile] = {
    "game_default": ConversionProfile(
        name="game_default",
        timing=TimingConfig(fps=12),
        anchor=AnchorConfig(mode="foot"),
        export=ExportConfig(aseprite=True, sheet_png_json=True, gif_preview=True),
    ),
    "unity_default": ConversionProfile(
        name="unity_default",
        timing=TimingConfig(fps=12),
        anchor=AnchorConfig(mode="foot"),
        export=ExportConfig(aseprite=True, sheet_png_json=True, gif_preview=True, trim=True),
    ),
    "godot_default": ConversionProfile(
        name="godot_default",
        timing=TimingConfig(fps=12),
        anchor=AnchorConfig(mode="foot"),
        export=ExportConfig(aseprite=True, sheet_png_json=True, gif_preview=True),
    ),
    "preview_only": ConversionProfile(
        name="preview_only",
        timing=TimingConfig(fps=12),
        anchor=AnchorConfig(mode="none"),
        export=ExportConfig(aseprite=False, sheet_png_json=False, gif_preview=True),
    ),
}


class Settings(BaseModel):
    """Application settings from environment variables."""
    aseprite_exe: Path = Field(description="Path to Aseprite executable")
    workspace_root: Path = Field(description="Workspace root directory")
    inbox_dir: Path = Field(description="Input directory")
    out_dir: Path = Field(description="Output directory")
    processed_dir: Path = Field(description="Processed files directory")
    failed_dir: Path = Field(description="Failed files directory")
    lua_scripts_dir: Path = Field(description="Lua scripts directory")
    default_profile: str = Field(default="game_default", description="Default conversion profile")

    @classmethod
    def from_env(cls, workspace_override: Optional[Path] = None) -> "Settings":
        """Create settings from environment variables."""
        # Get Aseprite executable path
        aseprite_exe_env = os.environ.get("ASEPRITE_EXE")
        if aseprite_exe_env:
            aseprite_exe = Path(aseprite_exe_env)
        else:
            # Try common locations on Windows
            common_paths = [
                Path(r"C:\Program Files\Aseprite\Aseprite.exe"),
                Path(r"C:\Program Files (x86)\Aseprite\Aseprite.exe"),
                Path.home() / "AppData" / "Local" / "Aseprite" / "Aseprite.exe",
            ]
            aseprite_exe = None
            for p in common_paths:
                if p.exists():
                    aseprite_exe = p
                    break
            if aseprite_exe is None:
                aseprite_exe = Path("aseprite")  # Assume in PATH

        # Get workspace root
        if workspace_override:
            workspace_root = workspace_override
        else:
            workspace_env = os.environ.get("SS_ANIM_WORKSPACE")
            if workspace_env:
                workspace_root = Path(workspace_env)
            else:
                # Default: ./workspace relative to package
                workspace_root = Path(__file__).parent.parent.parent / "workspace"

        workspace_root = workspace_root.resolve()

        # Lua scripts directory
        lua_scripts_dir = Path(__file__).parent.parent.parent / "aseprite_scripts"

        return cls(
            aseprite_exe=aseprite_exe,
            workspace_root=workspace_root,
            inbox_dir=workspace_root / "inbox",
            out_dir=workspace_root / "out",
            processed_dir=workspace_root / "processed",
            failed_dir=workspace_root / "failed",
            lua_scripts_dir=lua_scripts_dir.resolve(),
        )

    def ensure_directories(self) -> None:
        """Create workspace directories if they don't exist."""
        for d in [self.inbox_dir, self.out_dir, self.processed_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_profile(self, name: Optional[str] = None) -> ConversionProfile:
        """Get a conversion profile by name."""
        profile_name = name or self.default_profile
        if profile_name in PROFILES:
            return PROFILES[profile_name].model_copy(deep=True)
        return PROFILES["game_default"].model_copy(deep=True)


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings(workspace_override: Optional[Path] = None) -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None or workspace_override:
        _settings = Settings.from_env(workspace_override)
    return _settings

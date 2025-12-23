"""
FastMCP server for spritesheet to animation conversion.
Provides MCP tools for AI-assisted game asset automation.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config import Settings, get_settings, ConversionProfile
from .models import (
    JobSpec, ConvertResult, BatchReport, DetectionResult,
    WatchStatus, ServerStatus,
)
from .watcher import FolderWatcher
from .queue import JobQueue
from .detector import detect_grid
from .aseprite_runner import AsepriteRunner


# Global state
_settings: Optional[Settings] = None
_watcher: Optional[FolderWatcher] = None
_queue: Optional[JobQueue] = None


def get_state():
    """Get or initialize global state."""
    global _settings, _queue
    if _settings is None:
        _settings = get_settings()
        _settings.ensure_directories()
    if _queue is None:
        _queue = JobQueue(_settings)
    return _settings, _queue


# Create MCP server
server = Server("ss-anim-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="watch_start",
            description="Start watching inbox folder for new spritesheets. Files added to inbox will be automatically queued for conversion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "inbox_dir": {
                        "type": "string",
                        "description": "Optional: Custom inbox directory path",
                    },
                    "out_dir": {
                        "type": "string",
                        "description": "Optional: Custom output directory path",
                    },
                    "profile": {
                        "type": "string",
                        "description": "Conversion profile: 'game_default', 'unity_default', 'godot_default', 'preview_only'",
                        "default": "game_default",
                    },
                },
            },
        ),
        Tool(
            name="watch_stop",
            description="Stop watching the inbox folder.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="convert_inbox",
            description="Process all PNG files currently in the inbox folder. Best for 'add files then request conversion' workflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum files to process (default: 50)",
                        "default": 50,
                    },
                    "profile": {
                        "type": "string",
                        "description": "Conversion profile to use",
                        "default": "game_default",
                    },
                    "grid_rows": {
                        "type": "integer",
                        "description": "Override: Number of rows in spritesheet grid",
                    },
                    "grid_cols": {
                        "type": "integer",
                        "description": "Override: Number of columns in spritesheet grid",
                    },
                    "fps": {
                        "type": "integer",
                        "description": "Override: Animation FPS",
                    },
                },
            },
        ),
        Tool(
            name="convert_file",
            description="Convert a single spritesheet file to game animation assets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to the input spritesheet PNG",
                    },
                    "out_dir": {
                        "type": "string",
                        "description": "Optional: Output directory",
                    },
                    "profile": {
                        "type": "string",
                        "description": "Conversion profile to use",
                        "default": "game_default",
                    },
                    "grid_rows": {
                        "type": "integer",
                        "description": "Number of rows in spritesheet grid",
                    },
                    "grid_cols": {
                        "type": "integer",
                        "description": "Number of columns in spritesheet grid",
                    },
                    "fps": {
                        "type": "integer",
                        "description": "Animation FPS",
                    },
                },
                "required": ["input_path"],
            },
        ),
        Tool(
            name="status",
            description="Get current server status including queue length, recent results, and configuration.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="dry_run_detect",
            description="Analyze a spritesheet and return detected grid configuration without processing. Use to verify auto-detection before conversion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to the spritesheet to analyze",
                    },
                },
                "required": ["input_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    settings, queue = get_state()
    
    try:
        if name == "watch_start":
            result = await tool_watch_start(settings, queue, arguments)
        elif name == "watch_stop":
            result = await tool_watch_stop()
        elif name == "convert_inbox":
            result = await tool_convert_inbox(settings, queue, arguments)
        elif name == "convert_file":
            result = await tool_convert_file(settings, arguments)
        elif name == "status":
            result = await tool_status(settings, queue)
        elif name == "dry_run_detect":
            result = await tool_dry_run_detect(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def tool_watch_start(
    settings: Settings,
    queue: JobQueue,
    args: dict[str, Any],
) -> dict:
    """Start watching inbox folder."""
    global _watcher
    
    # Stop existing watcher if any
    if _watcher and _watcher.is_running:
        await _watcher.stop()
    
    # Get directories
    inbox_dir = Path(args.get("inbox_dir", settings.inbox_dir))
    out_dir = Path(args.get("out_dir", settings.out_dir))
    profile_name = args.get("profile", "game_default")
    
    # Ensure directories exist
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Get profile
    profile = settings.get_profile(profile_name)
    
    # Create callback for new files
    def on_new_file(path: Path):
        job = JobSpec.from_file(path, out_dir)
        asyncio.create_task(queue.enqueue(job, profile))
    
    # Create and start watcher
    _watcher = FolderWatcher(inbox_dir, on_new_file)
    await _watcher.start()
    
    # Start queue worker
    await queue.start()
    
    return {
        "status": "watching",
        "inbox_dir": str(inbox_dir),
        "out_dir": str(out_dir),
        "profile": profile_name,
        "message": f"Now watching {inbox_dir} for new spritesheets",
    }


async def tool_watch_stop() -> dict:
    """Stop watching inbox folder."""
    global _watcher
    
    if _watcher:
        await _watcher.stop()
        files_processed = _watcher.files_processed
        _watcher = None
        return {
            "status": "stopped",
            "files_processed": files_processed,
        }
    
    return {"status": "not_watching"}


async def tool_convert_inbox(
    settings: Settings,
    queue: JobQueue,
    args: dict[str, Any],
) -> dict:
    """Convert all files in inbox."""
    limit = args.get("limit", 50)
    profile_name = args.get("profile", "game_default")
    
    # Get profile and apply overrides
    profile = settings.get_profile(profile_name)
    
    if "grid_rows" in args:
        profile.grid.rows = args["grid_rows"]
    if "grid_cols" in args:
        profile.grid.cols = args["grid_cols"]
    if "fps" in args:
        profile.timing.fps = args["fps"]
    
    # Find files in inbox
    files = []
    for ext in [".png", ".jpg", ".jpeg"]:
        files.extend(settings.inbox_dir.glob(f"*{ext}"))
    
    files = sorted(files, key=lambda p: p.stat().st_mtime)[:limit]
    
    if not files:
        return {
            "status": "no_files",
            "message": f"No image files found in {settings.inbox_dir}",
        }
    
    # Process files
    report = await queue.process_batch(files, profile, settings.out_dir)
    
    # Build results summary
    results = []
    for r in report.results:
        item = {
            "name": r.job_name,
            "success": r.success,
        }
        if r.success:
            item["outputs"] = {
                "aseprite": str(r.aseprite_path) if r.aseprite_path else None,
                "sheet_png": str(r.sheet_png_path) if r.sheet_png_path else None,
                "sheet_json": str(r.sheet_json_path) if r.sheet_json_path else None,
                "gif": str(r.gif_path) if r.gif_path else None,
            }
            item["frames"] = r.frame_count
            if r.quality:
                item["anchor_jitter_rms"] = r.quality.anchor_jitter_rms_px
        else:
            item["error"] = r.error_message
        results.append(item)
    
    return {
        "status": "completed",
        "total": report.total_files,
        "successful": report.successful,
        "failed": report.failed,
        "results": results,
    }


async def tool_convert_file(settings: Settings, args: dict[str, Any]) -> dict:
    """Convert a single file."""
    input_path = Path(args["input_path"])
    
    if not input_path.exists():
        return {"error": f"File not found: {input_path}"}
    
    out_dir = Path(args.get("out_dir", settings.out_dir))
    profile_name = args.get("profile", "game_default")
    
    # Get profile and apply overrides
    profile = settings.get_profile(profile_name)
    
    if "grid_rows" in args:
        profile.grid.rows = args["grid_rows"]
    if "grid_cols" in args:
        profile.grid.cols = args["grid_cols"]
    if "fps" in args:
        profile.timing.fps = args["fps"]
    
    # Create job
    job = JobSpec.from_file(input_path, out_dir)
    job.grid = profile.grid
    job.timing = profile.timing
    
    # Auto-detect grid if not specified
    if profile.grid.rows == 1 and profile.grid.cols == 1:
        detection = detect_grid(input_path)
        if detection.detected and detection.grid:
            job.grid = detection.grid
    
    # Run conversion
    runner = AsepriteRunner(settings)
    result = await runner.run_conversion(job, profile)
    
    if result.success:
        return {
            "status": "success",
            "job_name": result.job_name,
            "outputs": {
                "aseprite": str(result.aseprite_path) if result.aseprite_path else None,
                "sheet_png": str(result.sheet_png_path) if result.sheet_png_path else None,
                "sheet_json": str(result.sheet_json_path) if result.sheet_json_path else None,
                "gif": str(result.gif_path) if result.gif_path else None,
                "meta": str(result.meta_path) if result.meta_path else None,
            },
            "frames": result.frame_count,
            "grid": {"rows": result.grid_rows, "cols": result.grid_cols},
            "fps": result.fps,
            "duration_seconds": result.duration_seconds,
        }
    else:
        return {
            "status": "failed",
            "job_name": result.job_name,
            "error": result.error_message,
            "error_log": str(result.error_log_path) if result.error_log_path else None,
        }


async def tool_status(settings: Settings, queue: JobQueue) -> dict:
    """Get server status."""
    global _watcher
    
    # Check Aseprite
    try:
        runner = AsepriteRunner(settings)
        aseprite_available = runner.is_available()
    except Exception:
        aseprite_available = False
    
    result = {
        "running": True,
        "aseprite_available": aseprite_available,
        "aseprite_path": str(settings.aseprite_exe),
        "workspace": {
            "root": str(settings.workspace_root),
            "inbox": str(settings.inbox_dir),
            "out": str(settings.out_dir),
            "processed": str(settings.processed_dir),
            "failed": str(settings.failed_dir),
        },
        "queue": {
            "length": queue.queue_length,
            "recent_success": queue.recent_success,
            "recent_failures": queue.recent_failures,
            "last_error": queue.last_error,
        },
    }
    
    if _watcher:
        result["watcher"] = {
            "watching": _watcher.is_running,
            "inbox_dir": str(_watcher.inbox_dir),
            "files_processed": _watcher.files_processed,
            "last_activity": str(_watcher.last_activity) if _watcher.last_activity else None,
        }
    else:
        result["watcher"] = {"watching": False}
    
    return result


async def tool_dry_run_detect(args: dict[str, Any]) -> dict:
    """Analyze spritesheet without processing."""
    input_path = Path(args["input_path"])
    
    if not input_path.exists():
        return {"error": f"File not found: {input_path}"}
    
    result = detect_grid(input_path)
    
    return {
        "detected": result.detected,
        "grid": {
            "rows": result.grid.rows if result.grid else 0,
            "cols": result.grid.cols if result.grid else 0,
            "offset_x": result.grid.offset_x if result.grid else 0,
            "offset_y": result.grid.offset_y if result.grid else 0,
        } if result.grid else None,
        "image": {
            "width": result.image_width,
            "height": result.image_height,
        },
        "frame": {
            "width": result.frame_width,
            "height": result.frame_height,
        },
        "confidence": result.confidence,
        "method": result.method,
        "notes": result.notes,
    }


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()

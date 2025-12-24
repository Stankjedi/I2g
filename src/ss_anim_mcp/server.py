"""
FastMCP server for spritesheet to animation conversion.
Provides MCP tools for AI-assisted game asset automation.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from .aseprite_runner import AsepriteError, AsepriteRunner
from .config import Settings, get_settings
from .detector import detect_grid
from .postprocess import get_post_processor
from .models import (
    JobOverrideError,
    JobSpec,
    apply_job_override,
    apply_tool_overrides,
    load_job_override,
)
from . import __version__
from .queue import JobQueue, create_failure_run_dir
from .watcher import FolderWatcher

logger = logging.getLogger(__name__)
_logging_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _logging_configured
    if _logging_configured:
        return

    root = logging.getLogger()
    if root.handlers:
        _logging_configured = True
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _logging_configured = True


def error_response(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": message, "error_code": error_code, "message": message}
    payload.update(extra)
    return payload


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_workspace_path(
    value: Optional[str],
    settings: Settings,
    *,
    allow_external_paths: bool,
    field_name: str,
    default: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    """
    Resolve a tool-provided path safely against workspace_root.

    - Expands `~`.
    - Resolves relative paths under `workspace_root`.
    - Returns a structured PATH_OUTSIDE_WORKSPACE error unless allow_external_paths is true.
    """
    if value is None or value == "":
        if default is None:
            return None, None
        path = default
    else:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = settings.workspace_root / candidate
        path = candidate

    resolved = path.resolve()
    workspace_root = settings.workspace_root.resolve()
    if not allow_external_paths and not _is_within(workspace_root, resolved):
        return None, error_response(
            "PATH_OUTSIDE_WORKSPACE",
            f"{field_name} must be inside workspace_root",
            field=field_name,
            path=str(resolved),
            workspace_root=str(workspace_root),
        )
    return resolved, None


def list_inbox_files(inbox_dir: Path, limit: int, exts: tuple[str, ...]) -> list[Path]:
    if limit <= 0:
        return []

    entries: list[tuple[float, str, Path]] = []
    try:
        with os.scandir(inbox_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                suffix = Path(entry.name).suffix.lower()
                if suffix not in exts:
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                entries.append((stat.st_mtime, entry.name, Path(entry.path)))
    except FileNotFoundError:
        return []

    if len(entries) > limit:
        selected = heapq.nsmallest(limit, entries)
    else:
        selected = sorted(entries)

    return [item[2] for item in selected]


@dataclass
class WorkspaceContext:
    settings: Settings
    queue: JobQueue
    watcher: Optional[FolderWatcher] = None


_contexts: dict[Path, WorkspaceContext] = {}


def _parse_workspace_root(args: dict[str, Any]) -> Optional[Path]:
    raw = args.get("workspace_root")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _get_context(workspace_root: Optional[Path]) -> WorkspaceContext:
    if workspace_root is None:
        settings = get_settings()
        settings.ensure_directories()
        key = settings.workspace_root.resolve()
    else:
        key = workspace_root.resolve()
        existing = _contexts.get(key)
        if existing:
            return existing
        settings = Settings.from_env(workspace_override=key)
        settings.ensure_directories()

    context = _contexts.get(key)
    if context is None:
        context = WorkspaceContext(settings=settings, queue=JobQueue(settings))
        _contexts[key] = context
    return context


server = Server("ss-anim-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="watch_start",
            description=(
                "Start watching inbox folder for new spritesheets. "
                "Files added to inbox will be automatically queued for conversion."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                    "inbox_dir": {"type": "string", "description": "Optional: Custom inbox directory path"},
                    "out_dir": {"type": "string", "description": "Optional: Custom output directory path"},
                    "processed_dir": {"type": "string", "description": "Optional: Custom processed directory path"},
                    "failed_dir": {"type": "string", "description": "Optional: Custom failed directory path"},
                    "allow_external_paths": {
                        "type": "boolean",
                        "description": "Allow directory overrides outside workspace_root (default: false)",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                },
            },
        ),
        Tool(
            name="convert_inbox",
            description="Process all PNG files currently in the inbox folder. Best for 'add files then request conversion' workflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                    "limit": {"type": "integer", "description": "Maximum files to process (default: 50)", "default": 50},
                    "profile": {"type": "string", "description": "Conversion profile to use", "default": "game_default"},
                    "grid_rows": {"type": "integer", "description": "Override: Number of rows in spritesheet grid"},
                    "grid_cols": {"type": "integer", "description": "Override: Number of columns in spritesheet grid"},
                    "fps": {"type": "integer", "description": "Override: Animation FPS"},
                    "processed_dir": {"type": "string", "description": "Optional: Custom processed directory path"},
                    "failed_dir": {"type": "string", "description": "Optional: Custom failed directory path"},
                    "allow_external_paths": {
                        "type": "boolean",
                        "description": "Allow directory overrides outside workspace_root (default: false)",
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
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                    "input_path": {"type": "string", "description": "Path to the input spritesheet PNG"},
                    "out_dir": {"type": "string", "description": "Optional: Output directory"},
                    "allow_external_paths": {
                        "type": "boolean",
                        "description": "Allow path arguments outside workspace_root (default: false)",
                    },
                    "profile": {"type": "string", "description": "Conversion profile to use", "default": "game_default"},
                    "grid_rows": {"type": "integer", "description": "Number of rows in spritesheet grid"},
                    "grid_cols": {"type": "integer", "description": "Number of columns in spritesheet grid"},
                    "fps": {"type": "integer", "description": "Animation FPS"},
                },
                "required": ["input_path"],
            },
        ),
        Tool(
            name="status",
            description="Get current server status including queue length, recent results, and configuration.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                },
            },
        ),
        Tool(
            name="dry_run_detect",
            description="Analyze a spritesheet and return detected grid configuration without processing. Use to verify auto-detection before conversion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                    "input_path": {"type": "string", "description": "Path to the spritesheet to analyze"},
                    "allow_external_paths": {
                        "type": "boolean",
                        "description": "Allow input_path outside workspace_root (default: false)",
                    },
                },
                "required": ["input_path"],
            },
        ),
        Tool(
            name="doctor",
            description="Run environment diagnostics (Aseprite path, workspace dirs, optional dependencies) without converting files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                },
            },
        ),
        Tool(
            name="cleanup_background",
            description="Remove background outside of dark outlines in AI-generated images. Uses flood-fill from edges, stopping at dark outline pixels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_root": {"type": "string", "description": "Optional: Workspace root override"},
                    "input_path": {"type": "string", "description": "Path to the input image"},
                    "output_path": {"type": "string", "description": "Optional: Output path (default: <input_stem>_cleaned.png)"},
                    "outline_threshold": {
                        "type": "integer",
                        "description": "Brightness threshold for outline detection (0-255, default: 30)",
                        "default": 30,
                    },
                    "fill_tolerance": {
                        "type": "integer",
                        "description": "Color similarity tolerance for flood fill (default: 50)",
                        "default": 50,
                    },
                    "preview_mode": {
                        "type": "boolean",
                        "description": "If true, show removed areas as red instead of transparent",
                        "default": False,
                    },
                    "allow_external_paths": {
                        "type": "boolean",
                        "description": "Allow path arguments outside workspace_root (default: false)",
                    },
                },
                "required": ["input_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    setup_logging()

    t0 = time.perf_counter()
    arg_keys = sorted(arguments.keys())
    logger.info("tool_call start: name=%s keys=%s", name, arg_keys)

    try:
        workspace_root = _parse_workspace_root(arguments)
        context = _get_context(workspace_root)

        if name == "watch_start":
            result = await tool_watch_start(context, arguments)
        elif name == "watch_stop":
            result = await tool_watch_stop(context)
        elif name == "convert_inbox":
            result = await tool_convert_inbox(context, arguments)
        elif name == "convert_file":
            result = await tool_convert_file(context, arguments)
        elif name == "status":
            result = await tool_status(context)
        elif name == "dry_run_detect":
            result = await tool_dry_run_detect(context, arguments)
        elif name == "doctor":
            result = await tool_doctor(context)
        elif name == "cleanup_background":
            result = await tool_cleanup_background(context, arguments)
        else:
            result = error_response("UNKNOWN_TOOL", f"Unknown tool: {name}")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info("tool_call end: name=%s elapsed_ms=%.1f", name, elapsed_ms)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except AsepriteError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.exception("tool_call error (AsepriteError): name=%s elapsed_ms=%.1f", name, elapsed_ms)
        result = error_response(e.error_code, str(e))
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except ValidationError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.exception("tool_call error (ValidationError): name=%s elapsed_ms=%.1f", name, elapsed_ms)
        result = error_response("VALIDATION_ERROR", "Validation error", details=str(e))
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.exception("tool_call error: name=%s elapsed_ms=%.1f", name, elapsed_ms)
        result = error_response("UNEXPECTED_EXCEPTION", str(e))
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def tool_watch_start(context: WorkspaceContext, args: dict[str, Any]) -> dict[str, Any]:
    """Start watching inbox folder."""
    if context.watcher and context.watcher.is_running:
        await context.watcher.stop()

    settings = context.settings
    queue = context.queue
    profile_name = args.get("profile", "game_default")
    allow_external_paths = bool(args.get("allow_external_paths", False))

    inbox_dir, err = _resolve_workspace_path(
        args.get("inbox_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="inbox_dir",
        default=settings.inbox_dir,
    )
    if err:
        return err

    out_dir, err = _resolve_workspace_path(
        args.get("out_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="out_dir",
        default=settings.out_dir,
    )
    if err:
        return err

    processed_dir, err = _resolve_workspace_path(
        args.get("processed_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="processed_dir",
    )
    if err:
        return err

    failed_dir, err = _resolve_workspace_path(
        args.get("failed_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="failed_dir",
    )
    if err:
        return err

    assert inbox_dir is not None
    assert out_dir is not None

    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    if processed_dir:
        processed_dir.mkdir(parents=True, exist_ok=True)
    if failed_dir:
        failed_dir.mkdir(parents=True, exist_ok=True)

    profile = settings.get_profile(profile_name)

    def on_new_file(path: Path) -> None:
        job = JobSpec.from_file(path, out_dir)
        job.processed_dir = processed_dir
        job.failed_dir = failed_dir
        job_profile = profile.model_copy(deep=True)

        try:
            override = load_job_override(path)
            if override is not None:
                apply_job_override(job_profile, override)
                if override.auto_detect_grid is not None:
                    job.auto_detect_grid = override.auto_detect_grid
        except JobOverrideError as e:
            logger.error("Invalid job override: input=%s override=%s error=%s", path, e.override_path, str(e))

            # Fail fast: write an error marker and move the input to failed.
            job_output_dir = out_dir / job.job_name
            job_output_dir.mkdir(parents=True, exist_ok=True)
            (job_output_dir / "error.txt").write_text(str(e) + "\n", encoding="utf-8")

            fail_root = failed_dir or settings.failed_dir
            fail_dir = create_failure_run_dir(fail_root, path.stem)
            dest = fail_dir / path.name
            counter = 1
            while dest.exists():
                dest = fail_dir / f"{path.stem}_{counter}{path.suffix}"
                counter += 1
            try:
                shutil.move(str(path), str(dest))
            except Exception:
                logger.exception("Failed to move input to failed dir: %s", path)
            error_log_path = fail_dir / "error.txt"
            error_log_path.write_text(str(e) + "\n", encoding="utf-8")
            (job_output_dir / "job.log").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "error_code": e.error_code,
                        "message": str(e),
                        "override_path": str(e.override_path) if e.override_path else None,
                        "failed_run_dir": str(fail_dir),
                        "failed_error_log_path": str(error_log_path),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return

        asyncio.create_task(queue.enqueue(job, job_profile))

    context.watcher = FolderWatcher(inbox_dir, on_new_file)
    await context.watcher.start()
    await queue.start()

    return {
        "status": "watching",
        "inbox_dir": str(inbox_dir),
        "out_dir": str(out_dir),
        "profile": profile_name,
        "message": f"Now watching {inbox_dir} for new spritesheets",
    }


async def tool_watch_stop(context: WorkspaceContext) -> dict[str, Any]:
    """Stop watching inbox folder."""
    if context.watcher:
        await context.watcher.stop()
        files_processed = context.watcher.files_processed
        context.watcher = None
        return {"status": "stopped", "files_processed": files_processed}

    return {"status": "not_watching"}


async def tool_convert_inbox(context: WorkspaceContext, args: dict[str, Any]) -> dict[str, Any]:
    """Convert all files in inbox."""
    settings = context.settings
    queue = context.queue
    limit = args.get("limit", 50)
    profile_name = args.get("profile", "game_default")
    allow_external_paths = bool(args.get("allow_external_paths", False))

    processed_dir, err = _resolve_workspace_path(
        args.get("processed_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="processed_dir",
    )
    if err:
        return err

    failed_dir, err = _resolve_workspace_path(
        args.get("failed_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="failed_dir",
    )
    if err:
        return err

    profile = settings.get_profile(profile_name)

    files = list_inbox_files(settings.inbox_dir, limit, (".png", ".jpg", ".jpeg"))

    if not files:
        return {"status": "no_files", "message": f"No image files found in {settings.inbox_dir}"}

    report = await queue.process_batch(
        files,
        profile,
        settings.out_dir,
        grid_rows=args.get("grid_rows"),
        grid_cols=args.get("grid_cols"),
        fps=args.get("fps"),
        processed_dir=processed_dir,
        failed_dir=failed_dir,
    )

    results: list[dict[str, Any]] = []
    for r in report.results:
        item: dict[str, Any] = {
            "name": r.job_name,
            "success": r.success,
            "error_code": r.error_code,
        }
        if r.success:
            item["outputs"] = {
                "aseprite": str(r.aseprite_path) if r.aseprite_path else None,
                "sheet_png": str(r.sheet_png_path) if r.sheet_png_path else None,
                "sheet_json": str(r.sheet_json_path) if r.sheet_json_path else None,
                "gif": str(r.gif_path) if r.gif_path else None,
                "meta": str(r.meta_path) if r.meta_path else None,
            }
            item["frames"] = r.frame_count
            if r.quality:
                item["anchor_jitter_rms"] = r.quality.anchor_jitter_rms_px
            item["logs"] = {
                "stdout": str(r.stdout_log_path) if r.stdout_log_path else None,
                "stderr": str(r.stderr_log_path) if r.stderr_log_path else None,
            }
        else:
            item["error"] = r.error_message
            item["message"] = r.error_message
            item["error_log"] = str(r.error_log_path) if r.error_log_path else None
            item["logs"] = {
                "stdout": str(r.stdout_log_path) if r.stdout_log_path else None,
                "stderr": str(r.stderr_log_path) if r.stderr_log_path else None,
            }
        results.append(item)

    return {
        "status": "completed",
        "total": report.total_files,
        "successful": report.successful,
        "failed": report.failed,
        "results": results,
    }


async def tool_convert_file(context: WorkspaceContext, args: dict[str, Any]) -> dict[str, Any]:
    """Convert a single file."""
    settings = context.settings
    allow_external_paths = bool(args.get("allow_external_paths", False))

    input_path, err = _resolve_workspace_path(
        args.get("input_path"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="input_path",
    )
    if err:
        return err

    assert input_path is not None
    if not input_path.exists():
        return error_response("FILE_NOT_FOUND", f"File not found: {input_path}", input_path=str(input_path))

    out_dir, err = _resolve_workspace_path(
        args.get("out_dir"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="out_dir",
        default=settings.out_dir,
    )
    if err:
        return err

    assert out_dir is not None
    profile_name = args.get("profile", "game_default")

    profile = settings.get_profile(profile_name)
    job = JobSpec.from_file(input_path, out_dir)

    try:
        override = load_job_override(input_path)
        if override is not None:
            apply_job_override(profile, override)
            if override.auto_detect_grid is not None:
                job.auto_detect_grid = override.auto_detect_grid
    except JobOverrideError as e:
        return error_response(
            e.error_code,
            str(e),
            override_path=str(e.override_path) if e.override_path else None,
        )

    apply_tool_overrides(
        profile,
        grid_rows=args.get("grid_rows"),
        grid_cols=args.get("grid_cols"),
        fps=args.get("fps"),
    )

    try:
        runner = AsepriteRunner(settings)
    except AsepriteError as e:
        return error_response(e.error_code, str(e), aseprite_path=str(settings.aseprite_exe))

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
            "logs": {
                "stdout": str(result.stdout_log_path) if result.stdout_log_path else None,
                "stderr": str(result.stderr_log_path) if result.stderr_log_path else None,
            },
        }

    return {
        "status": "failed",
        "job_name": result.job_name,
        "error": result.error_message,
        "error_code": result.error_code or "CONVERSION_FAILED",
        "message": result.error_message,
        "error_log": str(result.error_log_path) if result.error_log_path else None,
        "logs": {
            "stdout": str(result.stdout_log_path) if result.stdout_log_path else None,
            "stderr": str(result.stderr_log_path) if result.stderr_log_path else None,
        },
    }


async def tool_status(context: WorkspaceContext) -> dict[str, Any]:
    """Get server status."""
    settings = context.settings
    queue = context.queue

    try:
        runner = AsepriteRunner(settings)
        aseprite_available = runner.is_available()
    except Exception:
        aseprite_available = False

    result: dict[str, Any] = {
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
            "current_job": queue.current_job,
        },
    }

    if context.watcher:
        result["watcher"] = {
            "watching": context.watcher.is_running,
            "inbox_dir": str(context.watcher.inbox_dir),
            "files_processed": context.watcher.files_processed,
            "last_activity": str(context.watcher.last_activity) if context.watcher.last_activity else None,
            "error_count": context.watcher.error_count,
            "last_error": context.watcher.last_error,
            "last_scan_at": str(context.watcher.last_scan_at) if context.watcher.last_scan_at else None,
        }
    else:
        result["watcher"] = {"watching": False}

    return result


async def tool_dry_run_detect(context: WorkspaceContext, args: dict[str, Any]) -> dict[str, Any]:
    """Analyze spritesheet without processing."""
    settings = context.settings
    allow_external_paths = bool(args.get("allow_external_paths", False))

    input_path, err = _resolve_workspace_path(
        args.get("input_path"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="input_path",
    )
    if err:
        return err

    assert input_path is not None
    if not input_path.exists():
        return error_response("FILE_NOT_FOUND", f"File not found: {input_path}", input_path=str(input_path))

    result = detect_grid(input_path)

    return {
        "detected": result.detected,
        "grid": {
            "rows": result.grid.rows if result.grid else 0,
            "cols": result.grid.cols if result.grid else 0,
            "offset_x": result.grid.offset_x if result.grid else 0,
            "offset_y": result.grid.offset_y if result.grid else 0,
        }
        if result.grid
        else None,
        "image": {"width": result.image_width, "height": result.image_height},
        "frame": {"width": result.frame_width, "height": result.frame_height},
        "confidence": result.confidence,
        "method": result.method,
        "notes": result.notes,
    }


async def tool_doctor(context: WorkspaceContext) -> dict[str, Any]:
    """Return environment diagnostics without performing a conversion."""
    settings = context.settings
    findings: list[dict[str, Any]] = []

    def add_finding(level: str, code: str, message: str) -> None:
        findings.append({"level": level, "code": code, "message": message})

    def dir_status(path: Path) -> dict[str, Any]:
        exists = path.exists()
        writable = os.access(str(path), os.W_OK) if exists else os.access(str(path.parent), os.W_OK)
        return {"path": str(path), "exists": exists, "writable": writable}

    try:
        aseprite_available = False
        aseprite_message: Optional[str] = None
        try:
            runner = AsepriteRunner(settings)
            aseprite_available = runner.is_available()
        except AsepriteError as e:
            aseprite_available = False
            aseprite_message = str(e)

        if not aseprite_available:
            add_finding(
                "warning",
                "ASEPRITE_NOT_FOUND",
                "Aseprite is not available. Set ASEPRITE_EXE to the executable path or ensure `aseprite` is in PATH.",
            )

        lua_script_path = settings.lua_scripts_dir / "convert_sheet_to_anim.lua"
        if not lua_script_path.exists():
            add_finding(
                "warning",
                "LUA_SCRIPT_MISSING",
                f"Lua conversion script not found: {lua_script_path}",
            )

        workspace = {
            "root": dir_status(settings.workspace_root),
            "inbox": dir_status(settings.inbox_dir),
            "out": dir_status(settings.out_dir),
            "processed": dir_status(settings.processed_dir),
            "failed": dir_status(settings.failed_dir),
        }

        for key, info in workspace.items():
            if not info["exists"]:
                add_finding("warning", "WORKSPACE_DIR_MISSING", f"Workspace directory missing: {key} ({info['path']})")
            elif not info["writable"]:
                add_finding("warning", "WORKSPACE_DIR_NOT_WRITABLE", f"Workspace directory not writable: {key} ({info['path']})")

        post = get_post_processor()
        deps = {
            "ffmpeg": {"available": post.ffmpeg_available},
            "gifsicle": {"available": post.gifsicle_available},
        }

        if not deps["ffmpeg"]["available"]:
            add_finding("info", "FFMPEG_MISSING", "FFmpeg not found (only required for HQ GIF mode).")
        if not deps["gifsicle"]["available"]:
            add_finding("info", "GIFSICLE_MISSING", "gifsicle not found (optional GIF optimization).")

        status = "ok" if not any(f["level"] == "warning" for f in findings) else "warning"

        return {
            "status": status,
            "version": __version__,
            "python": {
                "version": sys.version.split()[0],
                "executable": sys.executable,
            },
            "aseprite": {
                "available": aseprite_available,
                "path": str(settings.aseprite_exe),
                "message": aseprite_message,
            },
            "workspace": workspace,
            "scripts": {
                "convert_sheet_to_anim": {"path": str(lua_script_path), "exists": lua_script_path.exists()},
            },
            "dependencies": deps,
            "findings": findings,
        }

    except Exception as e:
        logger.exception("doctor failed unexpectedly")
        return {
            "status": "warning",
            "version": __version__,
            "python": {"version": sys.version.split()[0], "executable": sys.executable},
            "findings": [
                {"level": "warning", "code": "DOCTOR_FAILED", "message": str(e)},
            ],
        }


async def tool_cleanup_background(context: WorkspaceContext, args: dict[str, Any]) -> dict[str, Any]:
    """Remove background outside of dark outlines in AI-generated images."""
    import subprocess
    import time as time_module

    settings = context.settings
    allow_external_paths = bool(args.get("allow_external_paths", False))

    input_path, err = _resolve_workspace_path(
        args.get("input_path"),
        settings,
        allow_external_paths=allow_external_paths,
        field_name="input_path",
    )
    if err:
        return err

    assert input_path is not None
    if not input_path.exists():
        return error_response("FILE_NOT_FOUND", f"File not found: {input_path}", input_path=str(input_path))

    # Determine output path
    output_path_arg = args.get("output_path")
    if output_path_arg:
        output_path, err = _resolve_workspace_path(
            output_path_arg,
            settings,
            allow_external_paths=allow_external_paths,
            field_name="output_path",
        )
        if err:
            return err
        assert output_path is not None
    else:
        output_path = input_path.with_name(f"{input_path.stem}_cleaned{input_path.suffix}")

    outline_threshold = args.get("outline_threshold", 30)
    fill_tolerance = args.get("fill_tolerance", 50)
    preview_mode = args.get("preview_mode", False)

    # Find the cleanup Lua script
    lua_script = settings.lua_scripts_dir / "cleanup_outline_bg.lua"
    if not lua_script.exists():
        return error_response(
            "CLEANUP_SCRIPT_NOT_FOUND",
            f"Cleanup Lua script not found: {lua_script}",
            lua_script=str(lua_script),
        )

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build Aseprite CLI command
    cmd = [
        str(settings.aseprite_exe),
        "-b",
        f"--script-param=input_path={input_path}",
        f"--script-param=output_path={output_path}",
        f"--script-param=outline_threshold={outline_threshold}",
        f"--script-param=fill_tolerance={fill_tolerance}",
        f"--script-param=preview_mode={'true' if preview_mode else 'false'}",
        "--script",
        str(lua_script),
    ]

    start_time = time_module.perf_counter()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed_ms = (time_module.perf_counter() - start_time) * 1000.0

        if proc.returncode != 0:
            return error_response(
                "ASEPRITE_CLEANUP_FAILED",
                f"Aseprite cleanup failed with code {proc.returncode}",
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                returncode=proc.returncode,
            )

        # Try to read result JSON from the output directory
        result_json_path = output_path.parent / "cleanup_result.json"
        if result_json_path.exists():
            try:
                result_data = json.loads(result_json_path.read_text(encoding="utf-8"))
                return {
                    "status": "success",
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "pixels_removed": result_data.get("pixels_removed", 0),
                    "image_width": result_data.get("image_width", 0),
                    "image_height": result_data.get("image_height", 0),
                    "removal_percentage": result_data.get("removal_percentage", 0.0),
                    "outline_threshold": outline_threshold,
                    "fill_tolerance": fill_tolerance,
                    "preview_mode": preview_mode,
                    "processing_time_ms": elapsed_ms,
                }
            except json.JSONDecodeError:
                pass

        # Basic success response if no result JSON
        return {
            "status": "success",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "outline_threshold": outline_threshold,
            "fill_tolerance": fill_tolerance,
            "preview_mode": preview_mode,
            "processing_time_ms": elapsed_ms,
        }

    except FileNotFoundError:
        return error_response(
            "ASEPRITE_NOT_FOUND",
            f"Aseprite executable not found: {settings.aseprite_exe}",
            aseprite_path=str(settings.aseprite_exe),
        )
    except Exception as e:
        return error_response("CLEANUP_ERROR", str(e))


async def run_server() -> None:
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point."""
    setup_logging()
    asyncio.run(run_server())


if __name__ == "__main__":
    main()

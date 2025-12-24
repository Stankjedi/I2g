# AI Agent Improvement Prompts

## Mandatory Execution Rules
1. Execute every prompt in order, starting from `[PROMPT-001]`. Do not skip or reorder.
2. Do not respond with text-only explanations. For each prompt, make real code changes using file-edit tools (`replace_string_in_file`, `multi_replace_string_in_file`, `create_file`).
3. After each prompt, run the verification commands listed in that prompt, fix failures, then proceed.
4. Keep changes minimal and focused on the prompt. Do not implement unrelated refactors.
5. Preserve existing style and conventions unless the prompt explicitly changes them.

## Execution Checklist

| # | Prompt ID | Title | Priority | Status |
|:---:|:---|:---|:---:|:---:|
| 1 | PROMPT-001 | Workspace Path Boundary Policy for Tool Arguments | P1 | ⬜ Pending |
| 2 | PROMPT-002 | Normalize Line Endings and Repository Text Rules | P2 | ⬜ Pending |
| 3 | PROMPT-003 | Lua Failure Metadata and Error Standardization | P2 | ⬜ Pending |
| 4 | PROMPT-004 | Grid Auto-Detection with Offset/Padding | P3 | ⬜ Pending |
| 5 | OPT-1 | Prune Watcher Internal State (Long-Run Stability) | OPT | ⬜ Pending |

Total: 5 prompts | Completed: 0 | Remaining: 5

## P1 Prompts

### [PROMPT-001] Workspace Path Boundary Policy for Tool Arguments
Execute this prompt now, then proceed to `[PROMPT-002]`.

Task description:
- Make all path-like tool arguments safe, predictable, and consistently validated against `workspace_root` by default.

Target files:
- `src/ss_anim_mcp/server.py`
- `src/ss_anim_mcp/config.py` (optional)
- `tests/` (add/update tests)

Steps:
1. Introduce a single path resolver/validator in `server.py` (or a small new module):
   - Inputs: raw string, `workspace_root`, `allow_external_paths`, and a `field_name`.
   - Behavior:
     - Expand `~` (home) if present.
     - If the path is relative, resolve it under `workspace_root`.
     - Resolve to an absolute path.
     - If `allow_external_paths` is false, reject paths outside `workspace_root` with `error_code=PATH_OUTSIDE_WORKSPACE`.
2. Apply the policy consistently across tool handlers:
   - `watch_start`: validate `inbox_dir`, `out_dir`, `processed_dir`, `failed_dir`.
   - `convert_inbox`: validate `processed_dir`, `failed_dir` (keep current behavior) and ensure the error payload includes the rejected `path` and `workspace_root`.
   - `convert_file`: add optional `allow_external_paths` and validate `input_path` and `out_dir`.
   - `dry_run_detect`: add optional `allow_external_paths` and validate `input_path`.
3. Ensure validation happens before any file I/O that could leak information about external paths (reject outside-workspace paths before checking `exists()`).
4. Add tests that do not require Aseprite:
   - `convert_file` rejects an external `input_path` by default and returns `PATH_OUTSIDE_WORKSPACE`.
   - `convert_file` accepts the same `input_path` when `allow_external_paths=true` (and still returns `FILE_NOT_FOUND` if it does not exist).
   - `watch_start` rejects external `inbox_dir`/`out_dir` when `allow_external_paths=false`.
5. Update tool schemas (`list_tools`) to include any new optional fields and keep changes additive.

Implementation requirements:
- Keep existing tool names and response shapes; only add new optional fields.
- Error responses must include `error_code`, `message`, and the relevant `path` and `workspace_root`.

Verification:
- `python -m compileall -q src`
- `pytest -q`

After completing this prompt, proceed to `[PROMPT-002]`.

## P2 Prompts

### [PROMPT-002] Normalize Line Endings and Repository Text Rules
Execute this prompt now, then proceed to `[PROMPT-003]`.

Task description:
- Remove line-ending inconsistencies (CRLF/stray control characters) and add repository-level rules to prevent regressions.

Target files:
- `.gitattributes` (create)
- `src/ss_anim_mcp/watcher.py`
- `aseprite_scripts/convert_sheet_to_anim.lua`
- `.vscode/mcp.json` (optional, only if tracked/used)

Steps:
1. Add a `.gitattributes` file that enforces LF for text files:
   - At minimum: `* text=auto eol=lf`
   - Add explicit rules for common extensions in this repo (`.py`, `.md`, `.lua`, `.json`, `.yml`, `.toml`).
2. Normalize line endings to LF for the affected files:
   - Rewrite the files so they no longer contain carriage returns (`\\r`).
   - Keep semantics unchanged; do not refactor logic in this prompt.
3. (Optional) Add a lightweight CI/test guard:
   - Add a small script (for example `scripts/check_crlf.py`) or a pytest test that fails if tracked source files contain `\\r`.
4. Ensure the repository still builds and tests pass.

Implementation requirements:
- No behavior changes beyond line-ending normalization and the addition of `.gitattributes`.
- If you add a CI/test guard, keep it fast and deterministic.

Verification:
- `python -m compileall -q src`
- `pytest -q`

After completing this prompt, proceed to `[PROMPT-003]`.

### [PROMPT-003] Lua Failure Metadata and Error Standardization
Execute this prompt now, then proceed to `[PROMPT-004]`.

Task description:
- Make failures diagnosable by ensuring Lua writes a structured `meta.json` for all error paths and Python surfaces that information as `error_code`/`error_message`.

Target files:
- `aseprite_scripts/convert_sheet_to_anim.lua`
- `src/ss_anim_mcp/aseprite_runner.py`
- `tests/` (add/update tests)

Steps:
1. In `convert_sheet_to_anim.lua`, introduce a small `write_meta(status, payload)` helper that:
   - Writes `meta.json` to `output_dir` even on early failures.
   - Includes: `status` (`success`/`failed`), `error_code`, `error_message`, and a minimal `params` snapshot (only safe, non-binary fields).
2. Replace all early `return` failure paths (missing `input_path`, missing `output_dir`, file not found, sprite open failure, invalid frame dimensions, etc.) to:
   - Print a concise error line.
   - Call `write_meta(\"failed\", ...)`.
   - Close any opened sprite if needed.
3. In `AsepriteRunner.run_conversion(...)`, after the subprocess exits with code 0:
   - Parse `meta.json` (if present and valid).
   - If `meta.status == \"failed\"`, return `ConvertResult(success=False, error_code=meta.error_code or \"LUA_REPORTED_FAILURE\", error_message=meta.error_message or \"Lua conversion failed\")`.
   - Keep the existing output contract validation as a separate check for missing outputs.
4. Add unit tests without invoking Aseprite:
   - Add a helper (for example `_interpret_meta_failure(meta: dict) -> tuple[Optional[str], Optional[str]]`) and test status parsing for both `success` and `failed` payloads.
   - Add a test fixture `meta.json` sample file (string) and ensure parsing is stable.

Implementation requirements:
- Do not require Aseprite/FFmpeg in tests.
- Do not change successful output paths or filenames; keep existing contracts.

Verification:
- `python -m compileall -q src`
- `pytest -q`

After completing this prompt, proceed to `[PROMPT-004]`.

## P3 Prompts

### [PROMPT-004] Grid Auto-Detection with Offset/Padding
Execute this prompt now, then proceed to `[OPT-1]`.

Task description:
- Improve grid auto-detection to estimate `offset_x/offset_y` and `pad_x/pad_y` for spritesheets with margins/padding, reducing the need for manual `.job.json` overrides.

Target files:
- `src/ss_anim_mcp/detector.py`
- `src/ss_anim_mcp/aseprite_runner.py` (only if needed for wiring)
- `tests/` (add new tests)

Steps:
1. Extend the detection algorithm in `GridDetector.detect(...)`:
   - Keep the current background color detection and gap analysis.
   - Add edge scanning to estimate offsets:
     - `offset_y`: number of top rows that are mostly background (by the same threshold logic).
     - `offset_x`: number of left columns that are mostly background.
   - After applying offsets, estimate padding:
     - Use gap groups to estimate typical gap thickness (for example median group width) and treat it as `pad_x`/`pad_y`.
   - Keep the algorithm conservative:
     - If estimates are uncertain or inconsistent, fall back to `0` for offset/pad and add a note.
2. Return a `GridConfig` that includes the estimated `offset_x/offset_y/pad_x/pad_y`.
3. Add tests using Pillow-generated synthetic spritesheets:
   - Create RGBA images with a solid background color and filled rectangles for frames.
   - Generate at least one case with non-zero offset and non-zero padding (for example 3x4 frames, 2px padding, 5px margin).
   - Save to `tmp_path`, run `detect_grid(...)`, and assert the detected rows/cols/offset/pad match expected values.
4. Keep wiring stable:
   - `AsepriteRunner` should continue to apply the detected `GridConfig` when `auto_detect_grid` is enabled and the effective grid is the default 1x1.

Implementation requirements:
- Keep detection deterministic and reasonably fast (do not scan every pixel in large images).
- Preserve existing behavior for spritesheets without padding/margins.

Verification:
- `python -m compileall -q src`
- `pytest -q`

After completing this prompt, proceed to `[OPT-1]`.

## OPT Prompts

### [OPT-1] Prune Watcher Internal State (Long-Run Stability)
Execute this prompt now, then proceed to the final completion section.

Task description:
- Prevent unbounded growth of watcher state in long-running watch mode to improve stability and memory usage.

Target files:
- `src/ss_anim_mcp/watcher.py`
- `tests/` (add/update tests)

Steps:
1. Make pruning testable:
   - Extract state cleanup into a helper method (for example `_prune_state(current_files: set[Path]) -> None`) or a small helper function.
2. In the polling loop (`_watch_loop_polling`):
   - After computing `current_files`, prune `seen_files` to keep only keys that are still in `current_files`.
   - Prune `_processed_files` to remove paths that no longer exist in `inbox_dir` (or are not in `current_files`).
3. In the watchfiles loop (`_watch_loop_watchfiles`):
   - Add a lightweight periodic prune (for example when `_processed_files` exceeds a threshold) that removes entries whose paths no longer exist.
4. Add unit tests:
   - Seed `_processed_files` and `seen_files` with many fake entries, run the prune helper once, and assert the collections shrink to the expected bounded set.
   - Ensure normal behavior remains unchanged for active files.

Implementation requirements:
- Avoid re-processing active files in the inbox.
- Keep public tool behavior unchanged; this is an internal stability improvement.

Verification:
- `python -m compileall -q src`
- `pytest -q`

## Final Completion
1. Confirm every checklist item status is updated to "Completed" in your final response.
2. Run final verification:
   - `python -m compileall -q src`
   - `pytest -q`
3. Print this completion message exactly:
   - `ALL PROMPTS COMPLETED. All pending improvement and optimization items from the latest report have been applied.`

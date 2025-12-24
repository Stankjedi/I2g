# AI Agent Improvement Prompts

## Mandatory Execution Rules
1. Execute every prompt in order, starting from `[PROMPT-001]`. Do not skip or reorder.
2. Do not respond with text-only explanations. For every change, use file-edit tools (`replace_string_in_file`, `multi_replace_string_in_file`, `create_file`).
3. After each prompt: run the verification commands, fix failures, then proceed to the next prompt.
4. Keep changes minimal and focused on the current prompt. Do not implement unrelated refactors.
5. Use Python 3.10+ (the code uses PEP 604 union types like `X | None`).
6. When a prompt updates documentation (for example `README.md`), keep the documentation written in Korean (the repository docs are Korean).
7. Do not add new runtime dependencies unless a prompt explicitly requires them.

## Execution Checklist

| # | Prompt ID | Title | Priority | Status |
|:---:|:---|:---|:---:|:---:|
| 1 | PROMPT-001 | CI Pipeline (Tests + Compile) | P1 | ⬜ Pending |
| 2 | PROMPT-002 | Release Artifacts & Cache Policy | P2 | ⬜ Pending |
| 3 | PROMPT-003 | Package Layout: Make `gui` Importable | P2 | ⬜ Pending |
| 4 | PROMPT-004 | CLI: Recursive Directory Processing | P2 | ⬜ Pending |
| 5 | PROMPT-005 | GUI: Presets / Profiles | P3 | ⬜ Pending |
| 6 | OPT-1 | Optimize cleanup_core Memory Footprint | OPT | ⬜ Pending |

Total: 6 prompts | Completed: 0 | Remaining: 6

## P1 Prompts

### [PROMPT-001] CI Pipeline (Tests + Compile)
Execute this prompt now, then proceed to `[PROMPT-002]`.

Task description:
- Add a GitHub Actions CI workflow that runs unit tests and a quick compile check on every pull request and push.

Target files:
- `.github/workflows/ci.yml` (new)
- `requirements-dev.txt` (update if needed)

Steps:
1. Create `.github/workflows/ci.yml` with the following workflow content:
   ```yaml
   name: CI
   on:
     pull_request:
     push:
       branches: ["master"]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
         - name: Install dependencies
           run: |
             python -m pip install --upgrade pip
             python -m pip install -r gui/requirements.txt -r requirements-dev.txt
         - name: Compile
           run: |
             python -m compileall -q gui
         - name: Tests
           run: |
             python -m pytest -q
   ```
2. Ensure `requirements-dev.txt` includes at least:
   - `pytest>=7.0`
3. Keep the workflow fast and deterministic:
   - Do not download external test assets.
   - Do not run GUI code in CI.

Implementation requirements:
- Use file-edit tools to apply all changes.
- Do not add new runtime dependencies.

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`

After completing this prompt, proceed to `[PROMPT-002]`.

## P2 Prompts

### [PROMPT-002] Release Artifacts & Cache Policy
Execute this prompt now, then proceed to `[PROMPT-003]`.

Task description:
- Define and enforce a clean repository policy: source code and specs stay tracked; build artifacts and caches do not.

Target files:
- `.gitignore`
- `README.md`
- `gui/dist/` (if committed artifacts exist, remove them)
- `.pytest_cache/` (if present, remove it)

Steps:
1. Update `.gitignore` (keep existing rules, only add missing ones) so these paths are ignored:
   - `gui/dist/`
   - `.pytest_cache/`
2. If committed build artifacts and caches exist under those paths, remove them from the repository contents.
3. Update `README.md` (in Korean) to clarify:
   - Releases are distributed via GitHub Releases (not committed binaries).
   - How to build the EXE locally using PyInstaller and the `.spec` file(s).
4. Do not remove documentation images under `docs/`.

Implementation requirements:
- Use file-edit tools to apply all changes.
- Keep behavior of the app unchanged (this is repository hygiene and documentation only).

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`

After completing this prompt, proceed to `[PROMPT-003]`.

### [PROMPT-003] Package Layout: Make `gui` Importable
Execute this prompt now, then proceed to `[PROMPT-004]`.

Task description:
- Turn `gui/` into a proper Python package and remove brittle `sys.path` hacks in tests, while keeping existing entrypoints working.

Target files:
- `gui/__init__.py` (new)
- `gui/main.py`
- `gui/cleanup_cli.py`
- `tests/test_cleanup_core.py`
- `tests/test_cleanup_cli.py`
- `gui/BackgroundCleaner_v0.0.2.spec` (update only if needed)

Steps:
1. Create `gui/__init__.py` (an empty file is acceptable).
2. Update imports to prefer package-relative imports with a safe fallback for script execution:
   - In `gui/main.py` and `gui/cleanup_cli.py`, use:
     ```python
     try:
         from .cleanup_core import CancelledError, cleanup_background
     except ImportError:
         from cleanup_core import CancelledError, cleanup_background
     ```
3. Update tests to use normal imports from the repository root (no `sys.path.insert`):
   - `from gui.cleanup_core import CancelledError, cleanup_background`
   - `from gui import cleanup_cli`
4. Ensure both execution modes remain valid:
   - `python gui/main.py` and `python -m gui.main`
   - `python gui/cleanup_cli.py ...` and `python -m gui.cleanup_cli ...`
5. Keep all public behavior unchanged (this is an import/layout change only).

Implementation requirements:
- Use file-edit tools to apply all changes.
- Do not add new runtime dependencies.

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`

After completing this prompt, proceed to `[PROMPT-004]`.

### [PROMPT-004] CLI: Recursive Directory Processing
Execute this prompt now, then proceed to `[PROMPT-005]`.

Task description:
- Add an opt-in recursive mode to the CLI so nested input directories can be batch-processed reliably.

Target files:
- `gui/cleanup_cli.py`
- `tests/test_cleanup_cli.py`
- `README.md` (update in Korean)

Steps:
1. Add a new flag:
   - `--recursive` (boolean, default: false)
2. Keep current behavior unchanged when `--recursive` is not provided.
3. When `--input` is a directory and `--recursive` is set:
   - Discover files via `Path.rglob("*")` filtered by supported extensions.
   - Sort file paths for deterministic processing order.
   - Preserve directory structure under `--output-dir`:
     - For each file, compute `rel = file_path.relative_to(input_dir)`.
     - Save to `output_dir / rel.parent / f"{file_path.stem}_cleaned.png"` (create parent dirs).
4. Extend tests:
   - Add a nested input folder with at least 1 image.
   - Run `cleanup_cli.main([... , "--recursive", ...])`.
   - Assert the output exists under the matching nested folder.
5. Update `README.md` with a recursive usage example and a note that directory structure is preserved in recursive mode.

Implementation requirements:
- Use file-edit tools to apply all changes.
- Keep exit codes and existing output naming stable for non-recursive mode.
- Do not import tkinter; the CLI must run headlessly.

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`

After completing this prompt, proceed to `[PROMPT-005]`.

## P3 Prompts

### [PROMPT-005] GUI: Presets / Profiles
Execute this prompt now, then proceed to `[OPT-1]`.

Task description:
- Add preset/profile support so users can save and reuse `Threshold`/`Dilation` combinations from the GUI.

Target files:
- `gui/main.py`
- `README.md` (optional; update in Korean if you add usage notes)

Steps:
1. Add a persistent preset store (no new dependencies):
   - Use `json` and store presets at `Path.home() / ".i2g_presets.json"`.
   - Use a simple schema: `{ "Preset Name": {"threshold": 20, "dilation": 50}, ... }`.
2. Add UI controls in the toolbar:
   - A preset dropdown (combobox or option menu)
   - A "Save Preset" action (ask for a name via `tkinter.simpledialog.askstring`)
   - A "Delete Preset" action (confirm via `messagebox`)
3. Preset behavior:
   - Selecting a preset updates the UI vars and entries (`threshold_var`, `dilation_var`).
   - Presets load on app startup; invalid JSON falls back to defaults with a user-visible warning.
   - Disable preset modifications while processing is running.
4. Add a few built-in presets (hardcoded defaults) and merge with user presets without overwriting user-defined names.

Implementation requirements:
- Use file-edit tools to apply all changes.
- Keep the cleanup algorithm API unchanged.

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`
- Manual check: run the GUI, save a preset, restart, and confirm it reloads and applies correctly.

After completing this prompt, proceed to `[OPT-1]`.

## OPT Prompts

### [OPT-1] Optimize cleanup_core Memory Footprint
Execute this prompt now, then proceed to the final completion section.

Task description:
- Reduce memory overhead in `cleanup_background()` for large images while preserving output quality and keeping tests stable.

Target files:
- `gui/cleanup_core.py`
- `tests/test_cleanup_core.py` (update/add tests if needed)

Steps:
1. Keep the public API and stats keys stable.
2. Replace large 2D boolean structures with compact flat arrays:
   - Convert `visited`, `removed`, `protected` into `bytearray(w * h)` (index: `i = y * w + x`).
   - Update all reads/writes accordingly.
3. Keep algorithm phases and semantics unchanged:
   - Edge flood fill (background discovery)
   - Outline protection
   - Frontier-based dilation
   - Isolated pixel cleanup
   - Apply removals and emit stats
4. Reduce avoidable overhead without changing results:
   - Avoid per-pass sorting of the frontier if output remains identical.
   - Minimize repeated attribute lookups inside hot loops (use local variables).
5. If you change internal ordering, ensure determinism:
   - `test_cleanup_is_deterministic` must still pass unchanged.

Implementation requirements:
- Use file-edit tools to apply all changes.
- Do not add new dependencies.
- Keep code readable (small helpers are fine; avoid unrelated refactors).

Verification:
- `python -m compileall -q gui`
- `python -m pytest -q`

## Final Completion
1. Confirm every checklist item is completed in your final response.
2. Run final verification:
   - `python -m compileall -q gui`
   - `python -m pytest -q`
3. Print this completion message exactly:
   - `ALL PROMPTS COMPLETED. All pending improvement and optimization items from the latest report have been applied.`

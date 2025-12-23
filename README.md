# I2g - Image to Game Animation

MCP server for automated spritesheet to game animation conversion using Aseprite CLI + Lua.

## Overview

**One PNG spritesheet → Auto split → Anchor alignment → Game-ready animation assets**

### Output Formats
- `anim.aseprite` - Source project file
- `anim_sheet.png` + `anim_sheet.json` - Game engine compatible (Unity/Godot)
- `anim_preview.gif` - Preview for communication

## User Flow

1. Drop a PNG spritesheet into `inbox/`
2. Ask AI: "Create game animation from the image I just added"
3. AI calls MCP tools → Auto processing
4. Results appear in `out/<name>/`

## Installation

### Prerequisites
- Python 3.10+
- [Aseprite](https://www.aseprite.org/) (CLI enabled)
- (Optional) FFmpeg, gifsicle for HQ GIF mode

### Setup

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/I2g.git
cd I2g

# Install dependencies
pip install -e .

# Set Aseprite path
export ASEPRITE_EXE="/path/to/aseprite"
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `watch_start` | Start folder watching |
| `watch_stop` | Stop watching |
| `convert_inbox` | Batch process inbox files |
| `convert_file` | Process single file |
| `status` | Get server status |
| `dry_run_detect` | Preview auto-detection |

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ASEPRITE_EXE` | Aseprite executable path | Yes |
| `SS_ANIM_WORKSPACE` | Workspace root path | No (default: `./workspace`) |

### JobSpec Override

Place `xxx.job.json` next to input file:

```json
{
  "grid": { "rows": 3, "cols": 4 },
  "timing": { "fps": 12, "loop_mode": "loop" },
  "anchor": { "mode": "foot" },
  "export": { "aseprite": true, "sheet_png_json": true, "gif_preview": true }
}
```

## Project Structure

```
I2g/
├── src/ss_anim_mcp/     # MCP server
├── aseprite_scripts/    # Lua conversion scripts
└── workspace/           # Default workspace
    ├── inbox/           # Input folder
    ├── out/             # Output folder
    ├── processed/       # Completed originals
    └── failed/          # Failed files with logs
```

## License

MIT

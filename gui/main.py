"""
I2g GUI Application
Pixel-focused tools with background cleanup, palette, resize, and animation helpers.
"""

__version__ = "0.0.3"

import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from PIL import Image, ImageTk

try:
    from .cleanup_core import CancelledError, cleanup_background
    from .tools.animation import slice_grid, align_frames
    from .tools.palette import (
        extract_palette,
        replace_color,
        merge_squares,
        split_squares,
        draw_brush,
        draw_line,
        flood_fill,
        adjust_alpha,
        clamp_alpha,
    )
    from .tools.pixel_perfect import pixel_perfect_outline
    from .tools.resize import resize_image
except ImportError:
    from cleanup_core import CancelledError, cleanup_background
    from tools.animation import slice_grid, align_frames
    from tools.palette import (
        extract_palette,
        replace_color,
        merge_squares,
        split_squares,
        draw_brush,
        draw_line,
        flood_fill,
        adjust_alpha,
        clamp_alpha,
    )
    from tools.pixel_perfect import pixel_perfect_outline
    from tools.resize import resize_image


class BackgroundCleanerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"I2g v{__version__} - Pixel Toolkit")
        self.root.geometry("1200x720")
        self.root.minsize(1000, 640)

        # State
        self.original_image: Image.Image | None = None
        self.working_image: Image.Image | None = None
        self.current_file: str | None = None
        self.processing = False
        self.cancel_event = threading.Event()

        # Animation state
        self.frames: list[Image.Image] = []
        self.frame_anchors: list[tuple[int, int] | None] = []
        self.current_frame_index = 0
        self.playing = False
        self.anchor_mode = False
        self.animation_after_id: str | None = None
        self.onion_var = tk.BooleanVar(value=False)

        # Presets
        self.preset_path = Path.home() / ".i2g_presets.json"
        self.built_in_presets = {
            "Default (20/50)": {"threshold": 20, "dilation": 50},
            "Soft Cleanup (10/30)": {"threshold": 10, "dilation": 30},
            "Strong Cleanup (15/80)": {"threshold": 15, "dilation": 80},
        }
        self.user_presets: dict[str, dict[str, int]] = {}
        self.presets: dict[str, dict[str, int]] = {}
        self.preset_var = tk.StringVar()
        self._load_presets()

        # View state
        self.zoom = 0
        self.min_zoom = 0.1
        self.max_zoom = 16.0
        self.offset = [0, 0]
        self._drag_start: tuple[int, int] | None = None
        self._display_scale = 1.0
        self._display_origin = (0, 0)

        # Drawing state
        self.draw_mode_var = tk.StringVar(value="Pan")
        self.draw_size_var = tk.IntVar(value=1)
        self.fill_tolerance_var = tk.IntVar(value=0)
        self.draw_color = (255, 255, 255, 255)
        self.line_start: tuple[int, int] | None = None

        # Color adjustment state
        self.r_var = tk.IntVar(value=255)
        self.g_var = tk.IntVar(value=255)
        self.b_var = tk.IntVar(value=255)
        self.a_var = tk.IntVar(value=255)
        self.alpha_scale_var = tk.DoubleVar(value=1.0)
        self.alpha_offset_var = tk.IntVar(value=0)
        self.alpha_low_threshold_var = tk.IntVar(value=40)
        self.alpha_low_value_var = tk.IntVar(value=0)
        self.alpha_high_threshold_var = tk.IntVar(value=200)
        self.alpha_high_value_var = tk.IntVar(value=255)

        # UI
        self._setup_style()
        self._setup_ui()
        self._setup_bindings()

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#e6e6e6")
        style.configure("TLabelframe", background="#1e1e1e", foreground="#e6e6e6")
        style.configure("TLabelframe.Label", background="#1e1e1e", foreground="#e6e6e6")
        style.configure("TButton", padding=6)
        style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#2a2a2a", foreground="#e6e6e6")

        self.root.configure(bg="#1e1e1e")

    def _setup_ui(self) -> None:
        self.bg_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.bg_canvas.pack(fill=tk.BOTH, expand=True)
        self.bg_canvas.bind("<Configure>", self._draw_gradient)

        self.main_frame = ttk.Frame(self.bg_canvas, padding=8)
        self.main_window = self.bg_canvas.create_window(0, 0, anchor=tk.NW, window=self.main_frame)

        # Top toolbar
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(toolbar, text="Open", command=self._open_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Save", command=self._save_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Reset Image", command=self._reset_to_original).pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(toolbar, text="Preset:").pack(side=tk.LEFT, padx=(4, 2))
        self.preset_combo = ttk.Combobox(toolbar, textvariable=self.preset_var, state="readonly", width=18)
        self.preset_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.save_preset_button = ttk.Button(toolbar, text="Save Preset", command=self._save_preset)
        self.save_preset_button.pack(side=tk.LEFT, padx=4)
        self.delete_preset_button = ttk.Button(toolbar, text="Delete Preset", command=self._delete_preset)
        self.delete_preset_button.pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="Reset View", command=self._reset_view).pack(side=tk.LEFT, padx=4)
        self.show_original_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Show Original", variable=self.show_original_var, command=self._display_image).pack(
            side=tk.LEFT, padx=4
        )

        # Main layout
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        self.left_panel = ttk.Frame(content_frame, width=280)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        self.right_panel = ttk.Frame(content_frame)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._build_left_panel()
        self._build_canvas()
        self._build_status_bar()

        self._refresh_presets(select_default=True)
        self._update_color_preview(self.draw_color)

    def _build_left_panel(self) -> None:
        notebook = ttk.Notebook(self.left_panel)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.background_tab = ttk.Frame(notebook)
        self.pixel_tab = ttk.Frame(notebook)
        self.resize_tab = ttk.Frame(notebook)
        self.palette_tab = ttk.Frame(notebook)
        self.animation_tab = ttk.Frame(notebook)

        notebook.add(self.background_tab, text="Background")
        notebook.add(self.pixel_tab, text="Pixel Perfect")
        notebook.add(self.resize_tab, text="Resize")
        notebook.add(self.palette_tab, text="Palette")
        notebook.add(self.animation_tab, text="Animation")

        self._build_background_tab()
        self._build_pixel_tab()
        self._build_resize_tab()
        self._build_palette_tab()
        self._build_animation_tab()
        notebook.select(self.palette_tab)

    def _build_background_tab(self) -> None:
        frame = self.background_tab
        ttk.Label(frame, text="Threshold").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.threshold_var = tk.IntVar(value=20)
        self.threshold_slider = ttk.Scale(frame, from_=5, to=80, variable=self.threshold_var, orient=tk.HORIZONTAL)
        self.threshold_slider.pack(fill=tk.X, padx=8)
        self.threshold_entry = ttk.Entry(frame, width=6)
        self.threshold_entry.insert(0, "20")
        self.threshold_entry.pack(anchor=tk.W, padx=8, pady=(4, 8))

        ttk.Label(frame, text="Dilation").pack(anchor=tk.W, padx=8, pady=(4, 2))
        self.dilation_var = tk.IntVar(value=50)
        self.dilation_slider = ttk.Scale(frame, from_=10, to=100, variable=self.dilation_var, orient=tk.HORIZONTAL)
        self.dilation_slider.pack(fill=tk.X, padx=8)
        self.dilation_entry = ttk.Entry(frame, width=6)
        self.dilation_entry.insert(0, "50")
        self.dilation_entry.pack(anchor=tk.W, padx=8, pady=(4, 8))

        self.process_button = ttk.Button(frame, text="Apply Cleanup", command=self._process_image)
        self.process_button.pack(fill=tk.X, padx=8, pady=(8, 4))
        self.cancel_button = ttk.Button(frame, text="Cancel", command=self._cancel_processing, state=tk.DISABLED)
        self.cancel_button.pack(fill=tk.X, padx=8, pady=(0, 8))

    def _build_pixel_tab(self) -> None:
        frame = self.pixel_tab
        ttk.Label(frame, text="Passes").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.pixel_passes_var = tk.IntVar(value=1)
        self.pixel_passes_slider = ttk.Scale(frame, from_=1, to=4, variable=self.pixel_passes_var, orient=tk.HORIZONTAL)
        self.pixel_passes_slider.pack(fill=tk.X, padx=8)
        ttk.Button(frame, text="Apply Pixel Perfect", command=self._apply_pixel_perfect).pack(
            fill=tk.X, padx=8, pady=(8, 8)
        )

    def _build_resize_tab(self) -> None:
        frame = self.resize_tab
        ttk.Label(frame, text="Scale (e.g., 2.0)").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.scale_var = tk.DoubleVar(value=2.0)
        self.scale_entry = ttk.Entry(frame)
        self.scale_entry.insert(0, "2.0")
        self.scale_entry.pack(fill=tk.X, padx=8)

        ttk.Label(frame, text="Method").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.resize_method_var = tk.StringVar(value="Nearest")
        self.resize_method_combo = ttk.Combobox(frame, textvariable=self.resize_method_var, state="readonly")
        self.resize_method_combo["values"] = ["Nearest", "Bilinear", "Bicubic"]
        self.resize_method_combo.pack(fill=tk.X, padx=8)

        ttk.Button(frame, text="Apply Resize", command=self._apply_resize).pack(fill=tk.X, padx=8, pady=(8, 8))

    def _build_palette_tab(self) -> None:
        frame = self.palette_tab
        ttk.Button(frame, text="Extract Palette", command=self._extract_palette).pack(fill=tk.X, padx=8, pady=(8, 4))

        self.palette_list = tk.Listbox(frame, height=6, selectmode=tk.SINGLE, bg="#222", fg="#e6e6e6")
        self.palette_list.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))

        ttk.Button(frame, text="Replace Selected Color", command=self._replace_selected_color).pack(
            fill=tk.X, padx=8, pady=(0, 6)
        )

        color_frame = ttk.Frame(frame)
        color_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.color_preview = tk.Canvas(color_frame, width=24, height=24, bg="#ffffff", highlightthickness=1)
        self.color_preview.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(color_frame, text="Pick Color", command=self._pick_draw_color).pack(side=tk.LEFT, padx=4)
        ttk.Button(color_frame, text="Use Selected", command=self._use_selected_palette_color).pack(
            side=tk.LEFT, padx=4
        )

        rgba_frame = ttk.Frame(frame)
        rgba_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        for label, var in (("R", self.r_var), ("G", self.g_var), ("B", self.b_var), ("A", self.a_var)):
            ttk.Label(rgba_frame, text=label).pack(side=tk.LEFT, padx=(0, 2))
            entry = ttk.Entry(rgba_frame, textvariable=var, width=4)
            entry.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(rgba_frame, text="Set Draw Color", command=self._apply_rgba_draw_color).pack(side=tk.LEFT, padx=4)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(frame, text="Draw Mode").pack(anchor=tk.W, padx=8, pady=(4, 2))
        self.draw_mode_combo = ttk.Combobox(frame, textvariable=self.draw_mode_var, state="readonly")
        self.draw_mode_combo["values"] = ["Pan", "Brush", "Line", "Fill"]
        self.draw_mode_combo.pack(fill=tk.X, padx=8)

        size_frame = ttk.Frame(frame)
        size_frame.pack(fill=tk.X, padx=8, pady=(4, 4))
        ttk.Label(size_frame, text="Size").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(size_frame, textvariable=self.draw_size_var, width=6).pack(side=tk.LEFT)
        ttk.Label(size_frame, text="Fill tol").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Entry(size_frame, textvariable=self.fill_tolerance_var, width=6).pack(side=tk.LEFT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(frame, text="Alpha Adjust").pack(anchor=tk.W, padx=8, pady=(4, 2))
        alpha_frame = ttk.Frame(frame)
        alpha_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(alpha_frame, text="Scale").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Entry(alpha_frame, textvariable=self.alpha_scale_var, width=6).pack(side=tk.LEFT)
        ttk.Label(alpha_frame, text="Offset").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(alpha_frame, textvariable=self.alpha_offset_var, width=6).pack(side=tk.LEFT)
        ttk.Button(alpha_frame, text="Apply", command=self._apply_alpha_adjust).pack(side=tk.LEFT, padx=6)

        clamp_frame = ttk.Frame(frame)
        clamp_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(clamp_frame, text="Low<= ").pack(side=tk.LEFT)
        ttk.Entry(clamp_frame, textvariable=self.alpha_low_threshold_var, width=4).pack(side=tk.LEFT)
        ttk.Label(clamp_frame, text="→").pack(side=tk.LEFT, padx=(2, 2))
        ttk.Entry(clamp_frame, textvariable=self.alpha_low_value_var, width=4).pack(side=tk.LEFT)
        ttk.Label(clamp_frame, text="High>= ").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Entry(clamp_frame, textvariable=self.alpha_high_threshold_var, width=4).pack(side=tk.LEFT)
        ttk.Label(clamp_frame, text="→").pack(side=tk.LEFT, padx=(2, 2))
        ttk.Entry(clamp_frame, textvariable=self.alpha_high_value_var, width=4).pack(side=tk.LEFT)
        ttk.Button(clamp_frame, text="Clamp", command=self._apply_alpha_clamp).pack(side=tk.LEFT, padx=6)

        ttk.Label(frame, text="Merge Squares (Downscale)").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.merge_block_var = tk.IntVar(value=2)
        self.merge_block_combo = ttk.Combobox(frame, textvariable=self.merge_block_var, state="readonly")
        self.merge_block_combo["values"] = [2, 3, 4]
        self.merge_block_combo.pack(fill=tk.X, padx=8)

        self.merge_method_var = tk.StringVar(value="Dominant")
        self.merge_method_combo = ttk.Combobox(frame, textvariable=self.merge_method_var, state="readonly")
        self.merge_method_combo["values"] = ["Dominant", "Average"]
        self.merge_method_combo.pack(fill=tk.X, padx=8, pady=(4, 4))

        self.merge_preserve_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Preserve Size", variable=self.merge_preserve_var).pack(
            anchor=tk.W, padx=8
        )
        ttk.Button(frame, text="Apply Merge", command=self._apply_merge).pack(fill=tk.X, padx=8, pady=(4, 8))

        ttk.Label(frame, text="Split Squares (Upscale)").pack(anchor=tk.W, padx=8, pady=(4, 2))
        self.split_block_var = tk.IntVar(value=2)
        self.split_block_combo = ttk.Combobox(frame, textvariable=self.split_block_var, state="readonly")
        self.split_block_combo["values"] = [2, 3, 4]
        self.split_block_combo.pack(fill=tk.X, padx=8)
        ttk.Button(frame, text="Apply Split", command=self._apply_split).pack(fill=tk.X, padx=8, pady=(4, 8))

    def _build_animation_tab(self) -> None:
        frame = self.animation_tab
        ttk.Label(frame, text="Slice Grid (cols x rows)").pack(anchor=tk.W, padx=8, pady=(8, 2))
        grid_frame = ttk.Frame(frame)
        grid_frame.pack(fill=tk.X, padx=8)
        self.anim_cols_var = tk.IntVar(value=1)
        self.anim_rows_var = tk.IntVar(value=1)
        ttk.Entry(grid_frame, textvariable=self.anim_cols_var, width=6).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(grid_frame, textvariable=self.anim_rows_var, width=6).pack(side=tk.LEFT)
        ttk.Button(frame, text="Create Frames", command=self._create_frames).pack(fill=tk.X, padx=8, pady=(6, 8))

        nav_frame = ttk.Frame(frame)
        nav_frame.pack(fill=tk.X, padx=8)
        ttk.Button(nav_frame, text="Prev", command=self._prev_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Next", command=self._next_frame).pack(side=tk.LEFT, padx=2)
        self.frame_label = ttk.Label(nav_frame, text="Frame: 0/0")
        self.frame_label.pack(side=tk.LEFT, padx=6)

        ttk.Label(frame, text="FPS").pack(anchor=tk.W, padx=8, pady=(8, 2))
        self.fps_var = tk.IntVar(value=6)
        ttk.Entry(frame, textvariable=self.fps_var, width=6).pack(anchor=tk.W, padx=8)

        anim_controls = ttk.Frame(frame)
        anim_controls.pack(fill=tk.X, padx=8, pady=(6, 6))
        ttk.Button(anim_controls, text="Play", command=self._play_animation).pack(side=tk.LEFT, padx=2)
        ttk.Button(anim_controls, text="Stop", command=self._stop_animation).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(
            anim_controls,
            text="Onion Skin",
            variable=self.onion_var,
            command=self._display_image,
        ).pack(side=tk.LEFT, padx=6)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(frame, text="Set Anchor Mode", command=self._toggle_anchor_mode).pack(
            fill=tk.X, padx=8, pady=(0, 4)
        )
        ttk.Button(frame, text="Align Frames", command=self._align_frames).pack(fill=tk.X, padx=8, pady=(0, 8))

    def _build_canvas(self) -> None:
        canvas_frame = ttk.Frame(self.right_panel)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#2a2a2a", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._display_image())

    def _build_status_bar(self) -> None:
        status_frame = ttk.Frame(self.main_frame)
        status_frame.pack(fill=tk.X, pady=(8, 0))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100, length=180)
        self.progress_bar.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT, padx=8)

        self.stats_label = ttk.Label(status_frame, text="")
        self.stats_label.pack(side=tk.RIGHT, padx=8)

    def _setup_bindings(self) -> None:
        self.threshold_var.trace_add("write", self._on_threshold_slider_change)
        self.dilation_var.trace_add("write", self._on_dilation_slider_change)

        self.threshold_entry.bind("<Return>", self._on_threshold_entry_change)
        self.threshold_entry.bind("<FocusOut>", self._on_threshold_entry_change)
        self.dilation_entry.bind("<Return>", self._on_dilation_entry_change)
        self.dilation_entry.bind("<FocusOut>", self._on_dilation_entry_change)

        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.palette_list.bind("<<ListboxSelect>>", self._on_palette_select)

    def _draw_gradient(self, event) -> None:
        width = event.width
        height = event.height
        self.bg_canvas.delete("gradient")

        top = (30, 30, 30)
        mid = (42, 42, 42)
        bottom = (20, 20, 20)

        for y in range(height):
            if y < height * 0.5:
                ratio = y / max(1, height * 0.5)
                r = int(top[0] + (mid[0] - top[0]) * ratio)
                g = int(top[1] + (mid[1] - top[1]) * ratio)
                b = int(top[2] + (mid[2] - top[2]) * ratio)
            else:
                ratio = (y - height * 0.5) / max(1, height * 0.5)
                r = int(mid[0] + (bottom[0] - mid[0]) * ratio)
                g = int(mid[1] + (bottom[1] - mid[1]) * ratio)
                b = int(mid[2] + (bottom[2] - mid[2]) * ratio)
            self.bg_canvas.create_line(0, y, width, y, fill=f"#{r:02x}{g:02x}{b:02x}", tags="gradient")

        self.bg_canvas.coords(self.main_window, 0, 0)
        self.bg_canvas.itemconfig(self.main_window, width=width, height=height)

    def _on_threshold_slider_change(self, *_):
        val = int(self.threshold_var.get())
        self.threshold_entry.delete(0, tk.END)
        self.threshold_entry.insert(0, str(val))

    def _on_dilation_slider_change(self, *_):
        val = int(self.dilation_var.get())
        self.dilation_entry.delete(0, tk.END)
        self.dilation_entry.insert(0, str(val))

    def _on_threshold_entry_change(self, _event):
        try:
            val = int(self.threshold_entry.get())
            val = max(5, min(80, val))
            self.threshold_var.set(val)
        except ValueError:
            pass

    def _on_dilation_entry_change(self, _event):
        try:
            val = int(self.dilation_entry.get())
            val = max(10, min(100, val))
            self.dilation_var.set(val)
        except ValueError:
            pass

    def _start_drag(self, event):
        if self.anchor_mode:
            return
        mode = self.draw_mode_var.get()
        if mode in ("Brush", "Line", "Fill"):
            ix, iy = self._canvas_to_image(event.x, event.y)
            if ix is None:
                return
            if mode == "Brush":
                self._apply_draw_brush(ix, iy)
            elif mode == "Line":
                self.line_start = (ix, iy)
            elif mode == "Fill":
                self._apply_fill(ix, iy)
            return
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self.anchor_mode:
            return
        mode = self.draw_mode_var.get()
        if mode == "Brush":
            ix, iy = self._canvas_to_image(event.x, event.y)
            if ix is not None:
                self._apply_draw_brush(ix, iy)
            return
        if mode == "Line":
            return
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self.offset[0] += dx
        self.offset[1] += dy
        self._display_image()

    def _end_drag(self, event):
        mode = self.draw_mode_var.get()
        if mode == "Line" and self.line_start is not None:
            ix, iy = self._canvas_to_image(event.x, event.y)
            if ix is not None:
                self._apply_draw_line(self.line_start, (ix, iy))
            self.line_start = None
        self._drag_start = None

    def _on_wheel(self, event):
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        if self.zoom == 0:
            self.zoom = self._display_scale
        self.zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        self._display_image()

    def _reset_view(self):
        self.zoom = 0
        self.offset = [0, 0]
        self._display_image()

    def _open_file(self):
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
            ("PNG files", "*.png"),
            ("All files", "*.*"),
        ]
        filepath = filedialog.askopenfilename(title="Select Image", filetypes=filetypes)
        if not filepath:
            return
        try:
            self.original_image = Image.open(filepath).convert("RGBA")
            self.working_image = self.original_image.copy()
            self.current_file = filepath
            self.frames = []
            self.frame_anchors = []
            self.current_frame_index = 0
            self._reset_view()
            self._display_image()
            self.status_label.config(text=f"Loaded: {Path(filepath).name}")
            self.stats_label.config(text=f"{self.original_image.width}x{self.original_image.height}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open image:\n{exc}")

    def _reset_to_original(self):
        if self.original_image is None:
            return
        self.working_image = self.original_image.copy()
        self.frames = []
        self.frame_anchors = []
        self.current_frame_index = 0
        self._display_image()

    def _save_file(self):
        image = self._get_active_image()
        if image is None:
            messagebox.showwarning("Warning", "No image to save.")
            return
        default_name = ""
        if self.current_file:
            base = Path(self.current_file)
            default_name = f"{base.stem}_edited.png"

        filepath = filedialog.asksaveasfilename(
            title="Save Result",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG files", "*.png")],
        )
        if filepath:
            try:
                image.save(filepath, "PNG")
                self.status_label.config(text=f"Saved: {Path(filepath).name}")
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to save image:\n{exc}")

    def _set_processing_state(self, processing: bool):
        self.processing = processing
        self.process_button.config(state=tk.DISABLED if processing else tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL if processing else tk.DISABLED)
        preset_state = tk.DISABLED if processing else "readonly"
        self.preset_combo.config(state=preset_state)
        self.save_preset_button.config(state=tk.DISABLED if processing else tk.NORMAL)
        self.delete_preset_button.config(state=tk.DISABLED if processing else tk.NORMAL)

    def _cancel_processing(self):
        if not self.processing:
            return
        self.cancel_event.set()
        self.cancel_button.config(state=tk.DISABLED)
        self.status_label.config(text="Cancelling...")

    def _process_image(self):
        image = self._get_active_image()
        if image is None:
            messagebox.showwarning("Warning", "Please open an image first.")
            return
        if self.processing:
            return

        self.cancel_event.clear()
        self._set_processing_state(True)
        self.status_label.config(text="Processing...")
        self.progress_var.set(0)

        def process_thread():
            try:
                def progress_callback(percent, message):
                    self.root.after(0, lambda: self.progress_var.set(percent))
                    self.root.after(0, lambda: self.status_label.config(text=message))

                result, stats = cleanup_background(
                    image,
                    outline_threshold=int(self.threshold_var.get()),
                    dilation_passes=int(self.dilation_var.get()),
                    progress_callback=progress_callback,
                    cancel_check=self.cancel_event.is_set,
                )

                def update_ui():
                    self._apply_to_current_image(result)
                    self.status_label.config(
                        text=f"Done! {stats['pixels_removed']:,}px ({stats['removal_percentage']:.1f}%)"
                    )
                    self._set_processing_state(False)

                self.root.after(0, update_ui)

            except CancelledError:
                def update_ui_cancelled():
                    self.progress_var.set(0)
                    self.status_label.config(text="Cancelled")
                    self._set_processing_state(False)

                self.root.after(0, update_ui_cancelled)

            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed:\n{exc}"))
                self.root.after(0, lambda: self.status_label.config(text="Error"))
                self.root.after(0, lambda: self._set_processing_state(False))

        threading.Thread(target=process_thread, daemon=True).start()

    def _apply_pixel_perfect(self):
        image = self._get_active_image()
        if image is None:
            return
        passes = max(1, int(self.pixel_passes_var.get()))
        result = pixel_perfect_outline(image, passes=passes)
        self._apply_to_current_image(result)
        self.status_label.config(text=f"Pixel Perfect applied ({passes} passes)")

    def _apply_resize(self):
        image = self._get_active_image()
        if image is None:
            return
        try:
            scale = float(self.scale_entry.get())
        except ValueError:
            messagebox.showwarning("Resize", "Invalid scale value.")
            return
        if scale <= 0:
            messagebox.showwarning("Resize", "Scale must be > 0.")
            return
        method = self.resize_method_var.get()
        result = resize_image(image, scale, method)
        self._apply_to_current_image(result)
        self.status_label.config(text=f"Resized x{scale}")

    def _extract_palette(self):
        image = self._get_active_image()
        if image is None:
            return
        palette = extract_palette(image, max_colors=64)
        self.palette_list.delete(0, tk.END)
        for (color, count) in palette:
            r, g, b, a = color
            self.palette_list.insert(tk.END, f"({r},{g},{b},{a}) x{count}")
        self._palette_cache = [color for (color, _count) in palette]
        self.status_label.config(text=f"Palette extracted ({len(palette)} colors)")

    def _replace_selected_color(self):
        image = self._get_active_image()
        if image is None:
            return
        if not hasattr(self, "_palette_cache"):
            messagebox.showwarning("Palette", "Extract palette first.")
            return
        selection = self.palette_list.curselection()
        if not selection:
            messagebox.showwarning("Palette", "Select a source color first.")
            return
        src_color = self._palette_cache[selection[0]]
        target_rgb, _ = colorchooser.askcolor(title="Pick replacement color")
        if target_rgb is None:
            return
        r, g, b = (int(v) for v in target_rgb)
        target = (r, g, b, src_color[3])
        result = replace_color(image, src_color, target, tolerance=0)
        self._apply_to_current_image(result)
        self.status_label.config(text="Color replaced")

    def _on_palette_select(self, _event) -> None:
        if not hasattr(self, "_palette_cache"):
            return
        selection = self.palette_list.curselection()
        if not selection:
            return
        color = self._palette_cache[selection[0]]
        self._update_color_preview(color)
        r, g, b, a = color
        self.r_var.set(r)
        self.g_var.set(g)
        self.b_var.set(b)
        self.a_var.set(a)

    def _update_color_preview(self, color: tuple[int, int, int, int]) -> None:
        r, g, b, _a = color
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self.color_preview.configure(bg=hex_color)

    def _set_draw_color(self, color: tuple[int, int, int, int]) -> None:
        self.draw_color = color
        self._update_color_preview(color)

    def _pick_draw_color(self) -> None:
        rgb, _ = colorchooser.askcolor(title="Pick draw color")
        if rgb is None:
            return
        r, g, b = (int(v) for v in rgb)
        color = (r, g, b, int(self.a_var.get()))
        self._set_draw_color(color)

    def _use_selected_palette_color(self) -> None:
        if not hasattr(self, "_palette_cache"):
            messagebox.showwarning("Palette", "Extract palette first.")
            return
        selection = self.palette_list.curselection()
        if not selection:
            messagebox.showwarning("Palette", "Select a palette color first.")
            return
        color = self._palette_cache[selection[0]]
        self._set_draw_color(color)
        r, g, b, a = color
        self.r_var.set(r)
        self.g_var.set(g)
        self.b_var.set(b)
        self.a_var.set(a)

    def _apply_rgba_draw_color(self) -> None:
        r = max(0, min(255, int(self.r_var.get())))
        g = max(0, min(255, int(self.g_var.get())))
        b = max(0, min(255, int(self.b_var.get())))
        a = max(0, min(255, int(self.a_var.get())))
        self._set_draw_color((r, g, b, a))

    def _apply_draw_brush(self, x: int, y: int) -> None:
        image = self._get_active_image()
        if image is None:
            return
        size = max(1, int(self.draw_size_var.get()))
        result = draw_brush(image, x, y, self.draw_color, size=size)
        self._apply_to_current_image(result)

    def _apply_draw_line(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        image = self._get_active_image()
        if image is None:
            return
        size = max(1, int(self.draw_size_var.get()))
        result = draw_line(image, start, end, self.draw_color, size=size)
        self._apply_to_current_image(result)

    def _apply_fill(self, x: int, y: int) -> None:
        image = self._get_active_image()
        if image is None:
            return
        tolerance = max(0, int(self.fill_tolerance_var.get()))
        result = flood_fill(image, x, y, self.draw_color, tolerance=tolerance)
        self._apply_to_current_image(result)

    def _apply_alpha_adjust(self) -> None:
        image = self._get_active_image()
        if image is None:
            return
        scale = float(self.alpha_scale_var.get())
        offset = int(self.alpha_offset_var.get())
        result = adjust_alpha(image, scale=scale, offset=offset)
        self._apply_to_current_image(result)
        self.status_label.config(text="Alpha adjusted")

    def _apply_alpha_clamp(self) -> None:
        image = self._get_active_image()
        if image is None:
            return
        low_t = int(self.alpha_low_threshold_var.get())
        low_v = int(self.alpha_low_value_var.get())
        high_t = int(self.alpha_high_threshold_var.get())
        high_v = int(self.alpha_high_value_var.get())
        result = clamp_alpha(image, low_t, low_v, high_t, high_v)
        self._apply_to_current_image(result)
        self.status_label.config(text="Alpha clamped")

    def _apply_merge(self):
        image = self._get_active_image()
        if image is None:
            return
        block = int(self.merge_block_var.get())
        method = self.merge_method_var.get()
        preserve = bool(self.merge_preserve_var.get())
        result = merge_squares(image, block, method=method, preserve_size=preserve)
        self._apply_to_current_image(result)
        self.status_label.config(text=f"Merged squares ({block}x{block})")

    def _apply_split(self):
        image = self._get_active_image()
        if image is None:
            return
        block = int(self.split_block_var.get())
        result = split_squares(image, block)
        self._apply_to_current_image(result)
        self.status_label.config(text=f"Split squares ({block}x{block})")

    def _create_frames(self):
        image = self.working_image
        if image is None:
            return
        cols = max(1, int(self.anim_cols_var.get()))
        rows = max(1, int(self.anim_rows_var.get()))
        self.frames = slice_grid(image, cols, rows)
        self.frame_anchors = [None] * len(self.frames)
        self.current_frame_index = 0
        self._update_frame_label()
        self._display_image()
        self.status_label.config(text=f"Frames created: {len(self.frames)}")

    def _prev_frame(self):
        if not self.frames:
            return
        self.current_frame_index = (self.current_frame_index - 1) % len(self.frames)
        self._update_frame_label()
        self._display_image()

    def _next_frame(self):
        if not self.frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self._update_frame_label()
        self._display_image()

    def _update_frame_label(self):
        total = len(self.frames)
        self.frame_label.config(text=f"Frame: {self.current_frame_index + 1}/{total}")

    def _play_animation(self):
        if not self.frames or self.playing:
            return
        self.playing = True
        self._animate_step()

    def _animate_step(self):
        if not self.playing or not self.frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self._update_frame_label()
        self._display_image()
        delay = max(1, int(1000 / max(1, self.fps_var.get())))
        self.animation_after_id = self.root.after(delay, self._animate_step)

    def _stop_animation(self):
        self.playing = False
        if self.animation_after_id is not None:
            self.root.after_cancel(self.animation_after_id)
            self.animation_after_id = None

    def _toggle_anchor_mode(self):
        self.anchor_mode = not self.anchor_mode
        state = "ON" if self.anchor_mode else "OFF"
        self.status_label.config(text=f"Anchor mode: {state}")

    def _align_frames(self):
        if not self.frames:
            return
        self.frames = align_frames(self.frames, self.frame_anchors, base_index=0)
        self._display_image()
        self.status_label.config(text="Frames aligned")

    def _on_canvas_click(self, event):
        if not self.anchor_mode:
            return
        image = self._get_active_image()
        if image is None:
            return
        ix, iy = self._canvas_to_image(event.x, event.y)
        if ix is None:
            return
        if self.frames:
            self.frame_anchors[self.current_frame_index] = (ix, iy)
        self.status_label.config(text=f"Anchor set: ({ix}, {iy})")
        self._display_image()

    def _canvas_to_image(self, x: int, y: int) -> tuple[int | None, int | None]:
        image = self._get_active_image()
        if image is None:
            return None, None
        x0, y0 = self._display_origin
        scale = self._display_scale
        ix = int((x - x0) / scale)
        iy = int((y - y0) / scale)
        if ix < 0 or iy < 0 or ix >= image.width or iy >= image.height:
            return None, None
        return ix, iy

    def _get_active_image(self) -> Image.Image | None:
        if self.show_original_var.get() and self.original_image is not None:
            return self.original_image
        if self.frames:
            return self.frames[self.current_frame_index]
        return self.working_image

    def _apply_to_current_image(self, image: Image.Image):
        if self.frames:
            self.frames[self.current_frame_index] = image
        else:
            self.working_image = image
        self._display_image()

    def _display_image(self):
        self.canvas.delete("all")
        image = self._get_active_image()
        if image is None:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="No image",
                fill="#666",
                font=("Arial", 14),
            )
            return

        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        iw, ih = image.size

        if self.zoom == 0:
            scale = min(cw / iw, ch / ih, 1.0)
        else:
            scale = self.zoom

        new_w = max(1, int(iw * scale))
        new_h = max(1, int(ih * scale))

        display = Image.new("RGBA", (new_w, new_h), (34, 34, 34, 255))
        resized = image.resize((new_w, new_h), Image.Resampling.NEAREST if scale > 2 else Image.Resampling.LANCZOS)
        display = Image.alpha_composite(display, resized)

        if self.onion_var.get() and self.frames and len(self.frames) > 1:
            prev_index = (self.current_frame_index - 1) % len(self.frames)
            ghost = self.frames[prev_index].resize(
                (new_w, new_h), Image.Resampling.NEAREST if scale > 2 else Image.Resampling.LANCZOS
            )
            alpha = ghost.getchannel("A").point(lambda a: int(a * 0.4))
            ghost.putalpha(alpha)
            display = Image.alpha_composite(display, ghost)

        photo = ImageTk.PhotoImage(display)
        self._canvas_photo = photo

        x = (cw - new_w) // 2 + self.offset[0]
        y = (ch - new_h) // 2 + self.offset[1]
        self._display_scale = scale
        self._display_origin = (x, y)
        self.canvas.create_image(x, y, anchor=tk.NW, image=photo)

        if self.frames and self.frame_anchors[self.current_frame_index] is not None:
            ax, ay = self.frame_anchors[self.current_frame_index]
            cx = x + int(ax * scale)
            cy = y + int(ay * scale)
            self.canvas.create_line(cx - 6, cy, cx + 6, cy, fill="#6fd3ff", width=2)
            self.canvas.create_line(cx, cy - 6, cx, cy + 6, fill="#6fd3ff", width=2)

    def _load_presets(self) -> None:
        self.user_presets = {}
        if not self.preset_path.exists():
            return
        try:
            with self.preset_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("Preset data must be a JSON object.")
            for name, values in data.items():
                if not isinstance(name, str) or not isinstance(values, dict):
                    continue
                threshold = values.get("threshold")
                dilation = values.get("dilation")
                if isinstance(threshold, (int, float)) and isinstance(dilation, (int, float)):
                    self.user_presets[name] = {"threshold": int(threshold), "dilation": int(dilation)}
        except Exception:
            self.user_presets = {}
            messagebox.showwarning("Presets", "Failed to load presets. Using defaults.")

    def _preset_names(self) -> list[str]:
        names = list(self.built_in_presets.keys())
        for name in sorted(self.user_presets.keys()):
            if name not in self.built_in_presets:
                names.append(name)
        return names

    def _refresh_presets(self, select_default: bool = False) -> None:
        self.presets = dict(self.built_in_presets)
        self.presets.update(self.user_presets)

        names = self._preset_names()
        self.preset_combo["values"] = names
        if not names:
            self.preset_var.set("")
            return

        current = self.preset_var.get()
        if select_default or current not in names:
            self.preset_var.set(names[0])
            self._apply_preset(names[0])

    def _apply_preset(self, name: str) -> None:
        preset = self.presets.get(name)
        if not preset:
            return
        self.threshold_var.set(int(preset["threshold"]))
        self.dilation_var.set(int(preset["dilation"]))

    def _on_preset_selected(self, _event) -> None:
        self._apply_preset(self.preset_var.get())

    def _save_presets(self) -> None:
        with self.preset_path.open("w", encoding="utf-8") as handle:
            json.dump(self.user_presets, handle, ensure_ascii=False, indent=2)

    def _save_preset(self) -> None:
        if self.processing:
            return
        name = simpledialog.askstring("Save Preset", "Preset name:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.built_in_presets and name not in self.user_presets:
            overwrite = messagebox.askyesno(
                "Save Preset", "This name matches a built-in preset. Overwrite it with your custom values?"
            )
            if not overwrite:
                return
        self.user_presets[name] = {
            "threshold": int(self.threshold_var.get()),
            "dilation": int(self.dilation_var.get()),
        }
        try:
            self._save_presets()
        except Exception as exc:
            messagebox.showerror("Save Preset", f"Failed to save presets:\n{exc}")
            return
        self._refresh_presets(select_default=False)
        self.preset_var.set(name)

    def _delete_preset(self) -> None:
        if self.processing:
            return
        name = self.preset_var.get()
        if not name:
            return
        if name not in self.user_presets:
            messagebox.showinfo("Delete Preset", "Built-in presets cannot be deleted.")
            return
        if not messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?"):
            return
        self.user_presets.pop(name, None)
        try:
            self._save_presets()
        except Exception as exc:
            messagebox.showerror("Delete Preset", f"Failed to save presets:\n{exc}")
            return
        self._refresh_presets(select_default=True)


def main():
    root = tk.Tk()
    app = BackgroundCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

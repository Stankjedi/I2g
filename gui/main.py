"""
Background Cleanup GUI Application
Real-time preview of AI image background removal.
"""

__version__ = "0.0.2"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
from pathlib import Path

from cleanup_core import cleanup_background


class BackgroundCleanerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"Background Cleaner v{__version__} - AI Image Post-Processing")
        self.root.geometry("1200x700")
        self.root.minsize(900, 600)
        
        # State
        self.original_image: Image.Image | None = None
        self.cleaned_image: Image.Image | None = None
        self.current_file: str | None = None
        self.processing = False
        
        # Separate zoom levels for each panel
        self.original_zoom = 0  # 0 = fit
        self.result_zoom = 0    # 0 = fit
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        
        # Pan offset for each panel
        self.original_offset = [0, 0]
        self.result_offset = [0, 0]
        
        # Drag state
        self._drag_start = None
        self._drag_panel = None
        
        self._setup_ui()
        self._setup_bindings()
    
    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text="📂 Open", command=self._open_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="💾 Save", command=self._save_file).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Label(toolbar, text="Threshold:").pack(side=tk.LEFT, padx=(5, 2))
        self.threshold_var = tk.IntVar(value=20)
        self.threshold_slider = ttk.Scale(toolbar, from_=5, to=80, variable=self.threshold_var, 
                                           orient=tk.HORIZONTAL, length=100)
        self.threshold_slider.pack(side=tk.LEFT)
        self.threshold_entry = ttk.Entry(toolbar, width=4)
        self.threshold_entry.insert(0, "20")
        self.threshold_entry.pack(side=tk.LEFT, padx=(2, 5))
        
        ttk.Label(toolbar, text="Dilation:").pack(side=tk.LEFT, padx=(5, 2))
        self.dilation_var = tk.IntVar(value=50)
        self.dilation_slider = ttk.Scale(toolbar, from_=10, to=100, variable=self.dilation_var,
                                          orient=tk.HORIZONTAL, length=100)
        self.dilation_slider.pack(side=tk.LEFT)
        self.dilation_entry = ttk.Entry(toolbar, width=4)
        self.dilation_entry.insert(0, "50")
        self.dilation_entry.pack(side=tk.LEFT, padx=(2, 5))
        
        ttk.Button(toolbar, text="🔄 Process", command=self._process_image).pack(side=tk.LEFT, padx=10)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(toolbar, text="Reset View", command=self._reset_view).pack(side=tk.LEFT, padx=5)
        ttk.Label(toolbar, text="Scroll:Zoom | Drag:Pan").pack(side=tk.LEFT, padx=5)
        
        # Image panels
        panels_frame = ttk.Frame(main_frame)
        panels_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (Original)
        left_frame = ttk.LabelFrame(panels_frame, text="Original", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.original_canvas = tk.Canvas(left_frame, bg='#2a2a2a', highlightthickness=0)
        self.original_canvas.pack(fill=tk.BOTH, expand=True)
        self.original_zoom_label = ttk.Label(left_frame, text="Fit")
        self.original_zoom_label.pack(side=tk.BOTTOM)
        
        # Right panel (Result)
        right_frame = ttk.LabelFrame(panels_frame, text="Result", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.result_canvas = tk.Canvas(right_frame, bg='#2a2a2a', highlightthickness=0)
        self.result_canvas.pack(fill=tk.BOTH, expand=True)
        self.result_zoom_label = ttk.Label(right_frame, text="Fit")
        self.result_zoom_label.pack(side=tk.BOTTOM)
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, 
                                             maximum=100, length=200)
        self.progress_bar.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready | Scroll:Zoom | Drag:Pan")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.stats_label = ttk.Label(status_frame, text="")
        self.stats_label.pack(side=tk.RIGHT, padx=5)
    
    def _setup_bindings(self):
        # Slider -> Entry sync
        self.threshold_var.trace_add('write', self._on_threshold_slider_change)
        self.dilation_var.trace_add('write', self._on_dilation_slider_change)
        
        # Entry -> Slider sync (on Enter key or focus out)
        self.threshold_entry.bind('<Return>', self._on_threshold_entry_change)
        self.threshold_entry.bind('<FocusOut>', self._on_threshold_entry_change)
        self.dilation_entry.bind('<Return>', self._on_dilation_entry_change)
        self.dilation_entry.bind('<FocusOut>', self._on_dilation_entry_change)
        
        self.original_canvas.bind('<Configure>', lambda e: self._display_original())
        self.result_canvas.bind('<Configure>', lambda e: self._display_result())
        
        # Zoom bindings
        self.original_canvas.bind('<MouseWheel>', self._on_original_wheel)
        self.result_canvas.bind('<MouseWheel>', self._on_result_wheel)
        
        # Drag bindings for original panel
        self.original_canvas.bind('<ButtonPress-1>', lambda e: self._start_drag(e, 'original'))
        self.original_canvas.bind('<B1-Motion>', self._on_drag)
        self.original_canvas.bind('<ButtonRelease-1>', self._end_drag)
        
        # Drag bindings for result panel
        self.result_canvas.bind('<ButtonPress-1>', lambda e: self._start_drag(e, 'result'))
        self.result_canvas.bind('<B1-Motion>', self._on_drag)
        self.result_canvas.bind('<ButtonRelease-1>', self._end_drag)
    
    def _start_drag(self, event, panel):
        self._drag_start = (event.x, event.y)
        self._drag_panel = panel
    
    def _on_threshold_slider_change(self, *args):
        val = int(self.threshold_var.get())
        self.threshold_entry.delete(0, tk.END)
        self.threshold_entry.insert(0, str(val))
    
    def _on_dilation_slider_change(self, *args):
        val = int(self.dilation_var.get())
        self.dilation_entry.delete(0, tk.END)
        self.dilation_entry.insert(0, str(val))
    
    def _on_threshold_entry_change(self, event):
        try:
            val = int(self.threshold_entry.get())
            val = max(5, min(80, val))  # Clamp to slider range
            self.threshold_var.set(val)
        except ValueError:
            pass
    
    def _on_dilation_entry_change(self, event):
        try:
            val = int(self.dilation_entry.get())
            val = max(10, min(100, val))  # Clamp to slider range
            self.dilation_var.set(val)
        except ValueError:
            pass
    
    def _on_drag(self, event):
        if self._drag_start is None:
            return
        
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        
        if self._drag_panel == 'original':
            self.original_offset[0] += dx
            self.original_offset[1] += dy
            self._display_original()
        elif self._drag_panel == 'result':
            self.result_offset[0] += dx
            self.result_offset[1] += dy
            self._display_result()
    
    def _end_drag(self, event):
        self._drag_start = None
        self._drag_panel = None
    
    def _on_original_wheel(self, event):
        factor = 1.2 if event.delta > 0 else 1/1.2
        self._zoom_original(factor)
    
    def _on_result_wheel(self, event):
        factor = 1.2 if event.delta > 0 else 1/1.2
        self._zoom_result(factor)
    
    def _zoom_original(self, factor):
        if self.original_zoom == 0:
            cw, ch = self.original_canvas.winfo_width(), self.original_canvas.winfo_height()
            if self.original_image and cw > 10 and ch > 10:
                iw, ih = self.original_image.size
                self.original_zoom = min(cw / iw, ch / ih, 1.0)
        
        self.original_zoom = max(self.min_zoom, min(self.max_zoom, self.original_zoom * factor))
        self.original_zoom_label.config(text=f"{int(self.original_zoom * 100)}%")
        self._display_original()
    
    def _zoom_result(self, factor):
        if self.result_zoom == 0:
            cw, ch = self.result_canvas.winfo_width(), self.result_canvas.winfo_height()
            if self.cleaned_image and cw > 10 and ch > 10:
                iw, ih = self.cleaned_image.size
                self.result_zoom = min(cw / iw, ch / ih, 1.0)
        
        self.result_zoom = max(self.min_zoom, min(self.max_zoom, self.result_zoom * factor))
        self.result_zoom_label.config(text=f"{int(self.result_zoom * 100)}%")
        self._display_result()
    
    def _reset_view(self):
        self.original_zoom = 0
        self.result_zoom = 0
        self.original_offset = [0, 0]
        self.result_offset = [0, 0]
        self.original_zoom_label.config(text="Fit")
        self.result_zoom_label.config(text="Fit")
        self._display_images()
    
    def _open_file(self):
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
            ("PNG files", "*.png"),
            ("All files", "*.*")
        ]
        filepath = filedialog.askopenfilename(title="Select Image", filetypes=filetypes)
        if filepath:
            try:
                self.original_image = Image.open(filepath).convert('RGBA')
                self.current_file = filepath
                self.cleaned_image = None
                self._reset_view()
                self._display_images()
                self.status_label.config(text=f"Loaded: {Path(filepath).name}")
                self.stats_label.config(text=f"{self.original_image.width}x{self.original_image.height}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open image:\n{e}")
    
    def _save_file(self):
        if self.cleaned_image is None:
            messagebox.showwarning("Warning", "No processed image to save.")
            return
        
        default_name = ""
        if self.current_file:
            base = Path(self.current_file)
            default_name = f"{base.stem}_cleaned.png"
        
        filepath = filedialog.asksaveasfilename(
            title="Save Result",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG files", "*.png")]
        )
        if filepath:
            try:
                self.cleaned_image.save(filepath, "PNG")
                self.status_label.config(text=f"Saved: {Path(filepath).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image:\n{e}")
    
    def _process_image(self):
        if self.original_image is None:
            messagebox.showwarning("Warning", "Please open an image first.")
            return
        
        if self.processing:
            return
        
        self.processing = True
        self.status_label.config(text="Processing...")
        self.progress_var.set(0)
        
        def process_thread():
            try:
                def progress_callback(percent, message):
                    self.root.after(0, lambda: self.progress_var.set(percent))
                    self.root.after(0, lambda: self.status_label.config(text=message))
                
                result, stats = cleanup_background(
                    self.original_image,
                    outline_threshold=int(self.threshold_var.get()),
                    dilation_passes=int(self.dilation_var.get()),
                    progress_callback=progress_callback
                )
                
                self.cleaned_image = result
                
                def update_ui():
                    self._display_result()
                    self.status_label.config(
                        text=f"Done! {stats['pixels_removed']:,}px ({stats['removal_percentage']:.1f}%)"
                    )
                    self.processing = False
                
                self.root.after(0, update_ui)
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed:\n{e}"))
                self.root.after(0, lambda: self.status_label.config(text="Error"))
                self.processing = False
        
        threading.Thread(target=process_thread, daemon=True).start()
    
    def _display_images(self):
        self._display_original()
        self._display_result()
    
    def _display_original(self):
        self._display_on_canvas(self.original_canvas, self.original_image, 
                                 self.original_zoom, self.original_offset, '_original_photo')
    
    def _display_result(self):
        self._display_on_canvas(self.result_canvas, self.cleaned_image,
                                 self.result_zoom, self.result_offset, '_result_photo')
    
    def _display_on_canvas(self, canvas: tk.Canvas, image: Image.Image | None, 
                            zoom: float, offset: list, photo_attr: str):
        canvas.delete("all")
        
        if image is None:
            canvas.create_text(
                canvas.winfo_width() // 2, canvas.winfo_height() // 2,
                text="No image", fill='#666666', font=('Arial', 14)
            )
            return
        
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        
        iw, ih = image.size
        
        if zoom == 0:  # Fit mode
            scale = min(cw / iw, ch / ih, 1.0)
        else:
            scale = zoom
        
        new_w, new_h = max(1, int(iw * scale)), max(1, int(ih * scale))
        
        # Use simpler background for better performance
        display = Image.new('RGBA', (new_w, new_h), (45, 45, 45, 255))
        
        # Composite the image
        resized = image.resize((new_w, new_h), Image.Resampling.NEAREST if scale > 2 else Image.Resampling.LANCZOS)
        display = Image.alpha_composite(display, resized)
        
        photo = ImageTk.PhotoImage(display)
        setattr(self, photo_attr, photo)
        
        # Center + offset
        x = (cw - new_w) // 2 + offset[0]
        y = (ch - new_h) // 2 + offset[1]
        canvas.create_image(x, y, anchor=tk.NW, image=photo)


def main():
    root = tk.Tk()
    
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    style.configure('TFrame', background='#2d2d2d')
    style.configure('TLabel', background='#2d2d2d', foreground='#ffffff')
    style.configure('TButton', padding=6)
    style.configure('TLabelframe', background='#2d2d2d')
    style.configure('TLabelframe.Label', background='#2d2d2d', foreground='#ffffff')
    
    root.configure(bg='#2d2d2d')
    
    app = BackgroundCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

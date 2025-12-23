"""
Data models for job specifications and reports.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field

from .config import GridConfig, TimingConfig, AnchorConfig, BackgroundConfig, ExportConfig


class JobSpec(BaseModel):
    """Complete job specification for a conversion task."""
    input_path: Path = Field(description="Path to input spritesheet")
    output_dir: Path = Field(description="Output directory for results")
    job_name: str = Field(description="Name for this job (used for output folder)")
    
    # Configuration sections (all optional, use profile defaults if not set)
    grid: Optional[GridConfig] = Field(default=None, description="Grid configuration override")
    timing: Optional[TimingConfig] = Field(default=None, description="Timing configuration override")
    anchor: Optional[AnchorConfig] = Field(default=None, description="Anchor configuration override")
    background: Optional[BackgroundConfig] = Field(default=None, description="Background configuration override")
    export: Optional[ExportConfig] = Field(default=None, description="Export configuration override")
    
    # Processing options
    auto_detect_grid: bool = Field(default=True, description="Auto-detect grid if not specified")
    profile_name: Optional[str] = Field(default=None, description="Profile to use as base")
    
    @classmethod
    def from_file(cls, input_path: Path, output_dir: Path, job_name: Optional[str] = None) -> "JobSpec":
        """Create a JobSpec from an input file path."""
        if job_name is None:
            job_name = input_path.stem
        return cls(
            input_path=input_path,
            output_dir=output_dir,
            job_name=job_name,
        )


class QualityMetrics(BaseModel):
    """Quality metrics for the conversion result."""
    anchor_jitter_rms_px: float = Field(default=0.0, description="RMS of anchor position variance")
    baseline_var_px: float = Field(default=0.0, description="Variance of baseline positions")
    bbox_var: float = Field(default=0.0, description="Variance of bounding box sizes")


class AnchorInfo(BaseModel):
    """Information about anchor points."""
    mode: str = Field(description="Anchor mode used")
    target_x: int = Field(description="Target anchor X position")
    target_y: int = Field(description="Target anchor Y position")
    per_frame_offsets: list[tuple[int, int]] = Field(default_factory=list, description="dx, dy per frame")


class ConvertResult(BaseModel):
    """Result of a single file conversion."""
    success: bool = Field(description="Whether conversion succeeded")
    input_path: Path = Field(description="Original input file path")
    job_name: str = Field(description="Job name")
    
    # Output paths (only set on success)
    aseprite_path: Optional[Path] = Field(default=None, description="Path to .aseprite file")
    sheet_png_path: Optional[Path] = Field(default=None, description="Path to spritesheet PNG")
    sheet_json_path: Optional[Path] = Field(default=None, description="Path to spritesheet JSON")
    gif_path: Optional[Path] = Field(default=None, description="Path to GIF preview")
    meta_path: Optional[Path] = Field(default=None, description="Path to meta.json")
    
    # Conversion info
    frame_count: int = Field(default=0, description="Number of frames")
    grid_rows: int = Field(default=0, description="Grid rows used")
    grid_cols: int = Field(default=0, description="Grid columns used")
    fps: int = Field(default=0, description="FPS used")
    
    # Quality metrics (only set on success)
    quality: Optional[QualityMetrics] = Field(default=None, description="Quality metrics")
    anchor_info: Optional[AnchorInfo] = Field(default=None, description="Anchor information")
    
    # Error info (only set on failure)
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    error_log_path: Optional[Path] = Field(default=None, description="Path to error log")
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.now, description="Start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")
    duration_seconds: float = Field(default=0.0, description="Processing duration in seconds")


class BatchReport(BaseModel):
    """Report for a batch conversion operation."""
    total_files: int = Field(description="Total files processed")
    successful: int = Field(default=0, description="Number of successful conversions")
    failed: int = Field(default=0, description="Number of failed conversions")
    skipped: int = Field(default=0, description="Number of skipped files")
    
    results: list[ConvertResult] = Field(default_factory=list, description="Individual results")
    
    started_at: datetime = Field(default_factory=datetime.now, description="Batch start time")
    completed_at: Optional[datetime] = Field(default=None, description="Batch completion time")
    
    def add_result(self, result: ConvertResult) -> None:
        """Add a result to the batch report."""
        self.results.append(result)
        if result.success:
            self.successful += 1
        else:
            self.failed += 1


class DetectionResult(BaseModel):
    """Result of automatic grid detection."""
    detected: bool = Field(description="Whether detection succeeded")
    grid: Optional[GridConfig] = Field(default=None, description="Detected grid configuration")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")
    
    image_width: int = Field(default=0, description="Input image width")
    image_height: int = Field(default=0, description="Input image height")
    frame_width: int = Field(default=0, description="Detected frame width")
    frame_height: int = Field(default=0, description="Detected frame height")
    
    method: str = Field(default="", description="Detection method used")
    notes: list[str] = Field(default_factory=list, description="Detection notes/warnings")


class WatchStatus(BaseModel):
    """Status of folder watching."""
    watching: bool = Field(description="Whether watching is active")
    inbox_dir: Optional[Path] = Field(default=None, description="Directory being watched")
    files_in_queue: int = Field(default=0, description="Files waiting in queue")
    files_processed: int = Field(default=0, description="Files processed since watch started")
    last_activity: Optional[datetime] = Field(default=None, description="Last activity timestamp")


class ServerStatus(BaseModel):
    """Overall server status."""
    running: bool = Field(default=True, description="Server is running")
    aseprite_available: bool = Field(description="Aseprite executable found")
    aseprite_path: Optional[Path] = Field(default=None, description="Aseprite executable path")
    
    workspace_root: Path = Field(description="Workspace root directory")
    inbox_dir: Path = Field(description="Inbox directory")
    out_dir: Path = Field(description="Output directory")
    
    watch_status: Optional[WatchStatus] = Field(default=None, description="Watch status if active")
    queue_length: int = Field(default=0, description="Current queue length")
    
    recent_success: int = Field(default=0, description="Recent successful conversions")
    recent_failures: int = Field(default=0, description="Recent failed conversions")
    last_error: Optional[str] = Field(default=None, description="Last error message")

"""
Grid detector module for automatic spritesheet grid detection.
Uses Pillow to analyze images and estimate grid dimensions.
"""

from pathlib import Path
from typing import Optional, Tuple, List
import math

from .config import GridConfig
from .models import DetectionResult


class GridDetector:
    """Detects spritesheet grid dimensions from image analysis."""
    
    def __init__(self, bg_tolerance: int = 10):
        self.bg_tolerance = bg_tolerance
    
    def detect(self, image_path: Path) -> DetectionResult:
        """
        Detect grid configuration from an image.
        Uses background color detection and gap analysis.
        """
        try:
            from PIL import Image
        except ImportError:
            return DetectionResult(
                detected=False,
                notes=["Pillow not installed, cannot detect grid"],
            )
        
        try:
            with Image.open(image_path) as img:
                img = img.convert("RGBA")
                width, height = img.size
                
                # Try to detect background color from corners
                bg_color = self._detect_background_color(img)
                
                # Find potential grid lines (rows of mostly background)
                h_gaps = self._find_gaps(img, bg_color, horizontal=True)
                v_gaps = self._find_gaps(img, bg_color, horizontal=False)
                
                # Estimate grid from gaps
                rows, row_height = self._estimate_grid_from_gaps(h_gaps, height)
                cols, col_width = self._estimate_grid_from_gaps(v_gaps, width)
                
                # Fallback: try common grid sizes
                if rows <= 1 or cols <= 1:
                    rows, cols, row_height, col_width = self._try_common_grids(width, height)
                
                # Calculate confidence
                confidence = self._calculate_confidence(
                    h_gaps, v_gaps, rows, cols, width, height
                )
                
                grid = GridConfig(
                    rows=rows,
                    cols=cols,
                    offset_x=0,
                    offset_y=0,
                    pad_x=0,
                    pad_y=0,
                )
                
                return DetectionResult(
                    detected=True,
                    grid=grid,
                    confidence=confidence,
                    image_width=width,
                    image_height=height,
                    frame_width=col_width,
                    frame_height=row_height,
                    method="gap_analysis" if h_gaps or v_gaps else "common_grid",
                    notes=[],
                )
                
        except Exception as e:
            return DetectionResult(
                detected=False,
                notes=[f"Error analyzing image: {str(e)}"],
            )
    
    def _detect_background_color(self, img) -> Tuple[int, int, int, int]:
        """Detect background color from image corners."""
        width, height = img.size
        corners = [
            (0, 0),
            (width - 1, 0),
            (0, height - 1),
            (width - 1, height - 1),
        ]
        
        colors = [img.getpixel(c) for c in corners]
        
        # Find most common corner color
        color_counts = {}
        for c in colors:
            key = c[:3]  # Ignore alpha for comparison
            color_counts[key] = color_counts.get(key, 0) + 1
        
        most_common = max(color_counts.items(), key=lambda x: x[1])
        r, g, b = most_common[0]
        
        # Get alpha from first matching corner
        for c in colors:
            if c[:3] == (r, g, b):
                return (r, g, b, c[3] if len(c) > 3 else 255)
        
        return (r, g, b, 255)
    
    def _is_background(self, pixel: Tuple, bg_color: Tuple) -> bool:
        """Check if a pixel matches the background color."""
        # Check alpha first - fully transparent is background
        if len(pixel) > 3 and pixel[3] < 10:
            return True
        
        # Check color match with tolerance
        for i in range(3):
            if abs(pixel[i] - bg_color[i]) > self.bg_tolerance:
                return False
        
        return True
    
    def _find_gaps(self, img, bg_color: Tuple, horizontal: bool) -> List[int]:
        """Find potential gap lines (mostly background pixels)."""
        width, height = img.size
        gaps = []
        
        if horizontal:
            # Find horizontal gaps (full rows of background)
            for y in range(height):
                bg_count = 0
                for x in range(width):
                    if self._is_background(img.getpixel((x, y)), bg_color):
                        bg_count += 1
                
                if bg_count > width * 0.95:  # 95%+ background = gap
                    gaps.append(y)
        else:
            # Find vertical gaps (full columns of background)
            for x in range(width):
                bg_count = 0
                for y in range(height):
                    if self._is_background(img.getpixel((x, y)), bg_color):
                        bg_count += 1
                
                if bg_count > height * 0.95:
                    gaps.append(x)
        
        return gaps
    
    def _estimate_grid_from_gaps(
        self, gaps: List[int], total_size: int
    ) -> Tuple[int, int]:
        """Estimate grid count and cell size from gap positions."""
        if not gaps:
            return 1, total_size
        
        # Group consecutive gaps (they form padding regions)
        gap_groups = []
        current_group = [gaps[0]]
        
        for gap in gaps[1:]:
            if gap - current_group[-1] <= 3:  # Within 3 pixels = same gap
                current_group.append(gap)
            else:
                gap_groups.append(current_group)
                current_group = [gap]
        gap_groups.append(current_group)
        
        # Count cells between gaps
        cells = len(gap_groups) + 1
        
        if cells > 1:
            # Calculate average cell size
            cell_size = total_size // cells
            return cells, cell_size
        
        return 1, total_size
    
    def _try_common_grids(
        self, width: int, height: int
    ) -> Tuple[int, int, int, int]:
        """Try common sprite sheet grid sizes."""
        # Common grids to try
        common = [
            (1, 4), (1, 6), (1, 8), (1, 12),  # Horizontal strips
            (4, 1), (6, 1), (8, 1),  # Vertical strips
            (2, 2), (2, 4), (4, 2),  # Small grids
            (3, 4), (4, 3), (4, 4),  # Medium grids
            (3, 3), (4, 4), (5, 5),  # Square grids
        ]
        
        best_score = 0
        best_grid = (1, 1)
        
        for rows, cols in common:
            if width % cols == 0 and height % rows == 0:
                # Perfect fit
                cell_w = width // cols
                cell_h = height // rows
                
                # Prefer grids with similar cell dimensions (roughly square)
                aspect_ratio = cell_w / cell_h if cell_h > 0 else 0
                score = 1.0 / (abs(aspect_ratio - 1.0) + 0.1)
                
                # Bonus for common frame counts
                frame_count = rows * cols
                if frame_count in [4, 6, 8, 12, 16]:
                    score *= 1.5
                
                if score > best_score:
                    best_score = score
                    best_grid = (rows, cols)
        
        rows, cols = best_grid
        return rows, cols, height // rows, width // cols
    
    def _calculate_confidence(
        self,
        h_gaps: List[int],
        v_gaps: List[int],
        rows: int,
        cols: int,
        width: int,
        height: int,
    ) -> float:
        """Calculate detection confidence score."""
        confidence = 0.5  # Base confidence
        
        # Boost if gaps were found
        if h_gaps:
            confidence += 0.2
        if v_gaps:
            confidence += 0.2
        
        # Boost if dimensions divide evenly
        if width % cols == 0:
            confidence += 0.05
        if height % rows == 0:
            confidence += 0.05
        
        # Cap at 1.0
        return min(confidence, 1.0)


def detect_grid(image_path: Path) -> DetectionResult:
    """Convenience function to detect grid from image."""
    detector = GridDetector()
    return detector.detect(image_path)

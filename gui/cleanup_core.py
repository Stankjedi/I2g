"""
cleanup_core.py
Python implementation of the background cleanup algorithm.
No Aseprite dependency - uses Pillow for image processing.
"""

from PIL import Image
from collections import deque
from typing import Tuple, Optional
import time


def get_brightness(r: int, g: int, b: int) -> float:
    """Calculate perceived brightness of a color."""
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_outline(pixel: Tuple[int, ...], threshold: int) -> bool:
    """Check if pixel is a dark outline."""
    if len(pixel) == 4 and pixel[3] < 128:  # Transparent
        return False
    r, g, b = pixel[:3]
    return get_brightness(r, g, b) <= threshold


def is_similar(p1: Tuple[int, ...], p2: Tuple[int, ...], tolerance: int) -> bool:
    """Check if two pixels are similar in color."""
    a1 = p1[3] if len(p1) == 4 else 255
    a2 = p2[3] if len(p2) == 4 else 255
    
    if a1 < 10 and a2 < 10:
        return True
    if (a1 < 10) != (a2 < 10):
        return False
    
    return (abs(p1[0] - p2[0]) <= tolerance and 
            abs(p1[1] - p2[1]) <= tolerance and 
            abs(p1[2] - p2[2]) <= tolerance)


def is_greenish(pixel: Tuple[int, ...]) -> bool:
    """Check if pixel has green tint (for edge remnant detection)."""
    if len(pixel) == 4 and pixel[3] < 10:
        return False
    r, g, b = pixel[:3]
    a = pixel[3] if len(pixel) == 4 else 255
    # Green dominant or semi-transparent
    return (g > r - 15 and g > b - 15 and g > 20) or (a < 200)


def cleanup_background(
    image: Image.Image,
    outline_threshold: int = 20,
    fill_tolerance: int = 80,
    dilation_passes: int = 50,
    progress_callback: Optional[callable] = None
) -> Tuple[Image.Image, dict]:
    """
    Remove background outside of dark outlines.
    
    Args:
        image: Input PIL Image (RGBA)
        outline_threshold: Brightness threshold for outline detection (0-255)
        fill_tolerance: Color similarity tolerance for flood fill
        dilation_passes: Number of edge dilation passes
        progress_callback: Optional callback(percent, message) for progress updates
    
    Returns:
        Tuple of (cleaned image, stats dict)
    """
    start_time = time.time()
    
    # Ensure RGBA mode
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    img = image.copy()
    pixels = img.load()
    w, h = img.size
    
    # Track removed pixels
    removed = [[False] * w for _ in range(h)]
    pixels_to_remove = []
    
    if progress_callback:
        progress_callback(5, "Flood fill from edges...")
    
    # STEP 1: Flood fill from edges
    visited = [[False] * w for _ in range(h)]
    queue = deque()
    
    # Add edge pixels to queue
    for x in range(w):
        queue.append((x, 0))
        queue.append((x, h - 1))
    for y in range(1, h - 1):
        queue.append((0, y))
        queue.append((w - 1, y))
    
    # Get corner reference colors
    corner_pixels = [
        pixels[0, 0], pixels[w-1, 0],
        pixels[0, h-1], pixels[w-1, h-1]
    ]
    
    while queue:
        x, y = queue.popleft()
        
        if x < 0 or x >= w or y < 0 or y >= h:
            continue
        if visited[y][x]:
            continue
        visited[y][x] = True
        
        px = pixels[x, y]
        
        if is_outline(px, outline_threshold):
            continue
        
        # Check if similar to any corner (background)
        match_bg = any(is_similar(px, cpx, fill_tolerance) for cpx in corner_pixels)
        
        alpha = px[3] if len(px) == 4 else 255
        if match_bg or alpha < 128:
            pixels_to_remove.append((x, y))
            removed[y][x] = True
            queue.append((x - 1, y))
            queue.append((x + 1, y))
            queue.append((x, y - 1))
            queue.append((x, y + 1))
    
    if progress_callback:
        progress_callback(40, "Edge dilation...")
    
    # STEP 2: Edge dilation - MORE CONSERVATIVE
    # Only remove pixels that are:
    # 1. Adjacent to removed area
    # 2. NOT outline pixels (already protected)
    # 3. Similar to background colors OR semi-transparent
    edge_removed = 0
    neighbors_8 = [(-1, 0), (1, 0), (0, -1), (0, 1), 
                   (-1, -1), (1, -1), (-1, 1), (1, 1)]
    
    # First, mark all outline pixels as PROTECTED (never remove)
    protected = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            px = pixels[x, y]
            if is_outline(px, outline_threshold):
                protected[y][x] = True
    
    # Dilation: only remove background-like pixels adjacent to removed areas
    for pass_num in range(dilation_passes):
        new_removals = []
        
        for y in range(h):
            for x in range(w):
                if removed[y][x] or protected[y][x]:
                    continue
                
                px = pixels[x, y]
                
                # Skip if this pixel is clearly content (not background-like)
                alpha = px[3] if len(px) == 4 else 255
                
                # Only consider removing if:
                # - Semi-transparent (alpha < 200), OR
                # - Similar to corner background colors, OR
                # - Greenish (background remnant color)
                is_bg_like = alpha < 200
                if not is_bg_like and is_greenish(px):
                    is_bg_like = True
                if not is_bg_like:
                    for cpx in corner_pixels:
                        if is_similar(px, cpx, fill_tolerance):
                            is_bg_like = True
                            break
                
                if not is_bg_like:
                    continue
                
                # Check if adjacent to removed pixel
                adj_removed = False
                for dx, dy in neighbors_8:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and removed[ny][nx]:
                        adj_removed = True
                        break
                
                if adj_removed:
                    new_removals.append((x, y))
        
        for x, y in new_removals:
            removed[y][x] = True
            pixels_to_remove.append((x, y))
            edge_removed += 1
        
        if not new_removals:
            break
        
        if progress_callback:
            progress = 40 + int(40 * (pass_num + 1) / dilation_passes)
            progress_callback(progress, f"Edge dilation pass {pass_num + 1}...")
    
    if progress_callback:
        progress_callback(85, "Final cleanup...")
    
    # STEP 3: Isolated pixel cleanup
    isolated_removed = 0
    for y in range(h):
        for x in range(w):
            if removed[y][x]:
                continue
            
            px = pixels[x, y]
            if is_outline(px, outline_threshold):
                continue
            if not is_greenish(px):
                continue
            
            adj_outline = False
            adj_transparent = False
            
            for dx, dy in neighbors_8:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if removed[ny][nx]:
                        adj_transparent = True
                    else:
                        npx = pixels[nx, ny]
                        if is_outline(npx, outline_threshold):
                            adj_outline = True
                        if len(npx) == 4 and npx[3] < 50:
                            adj_transparent = True
                else:
                    adj_transparent = True
            
            if adj_outline and adj_transparent:
                pixels_to_remove.append((x, y))
                removed[y][x] = True
                isolated_removed += 1
    
    if progress_callback:
        progress_callback(95, "Applying changes...")
    
    # Apply removals
    for x, y in pixels_to_remove:
        pixels[x, y] = (0, 0, 0, 0)
    
    elapsed = time.time() - start_time
    
    stats = {
        'pixels_removed': len(pixels_to_remove),
        'edge_pixels_removed': edge_removed,
        'isolated_pixels_removed': isolated_removed,
        'image_width': w,
        'image_height': h,
        'total_pixels': w * h,
        'removal_percentage': (len(pixels_to_remove) / (w * h)) * 100,
        'processing_time_ms': elapsed * 1000,
        'outline_threshold': outline_threshold,
        'dilation_passes': dilation_passes
    }
    
    if progress_callback:
        progress_callback(100, "Complete!")
    
    return img, stats

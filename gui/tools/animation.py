from PIL import Image


def slice_grid(image: Image.Image, columns: int, rows: int) -> list[Image.Image]:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    if columns <= 0 or rows <= 0:
        return [image.copy()]
    frame_w = w // columns
    frame_h = h // rows
    if frame_w <= 0 or frame_h <= 0:
        return [image.copy()]

    frames = []
    for row in range(rows):
        for col in range(columns):
            left = col * frame_w
            upper = row * frame_h
            right = left + frame_w
            lower = upper + frame_h
            frames.append(image.crop((left, upper, right, lower)))
    return frames


def align_frames(
    frames: list[Image.Image],
    anchors: list[tuple[int, int] | None],
    base_index: int = 0,
) -> list[Image.Image]:
    if not frames:
        return []
    base = anchors[base_index] if base_index < len(anchors) else None
    if base is None:
        return frames
    base_x, base_y = base

    aligned = []
    for idx, frame in enumerate(frames):
        anchor = anchors[idx] if idx < len(anchors) else None
        if anchor is None:
            aligned.append(frame)
            continue
        ax, ay = anchor
        dx = base_x - ax
        dy = base_y - ay
        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.paste(frame, (dx, dy))
        aligned.append(canvas)
    return aligned

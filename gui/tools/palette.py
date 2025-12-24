from collections import Counter, deque
from PIL import Image, ImageDraw


def extract_palette(image: Image.Image, max_colors: int = 64) -> list[tuple[tuple[int, int, int, int], int]]:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    counts = Counter(image.getdata())
    return counts.most_common(max_colors)


def replace_color(
    image: Image.Image,
    source: tuple[int, int, int, int],
    target: tuple[int, int, int, int],
    tolerance: int = 0,
) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    src_r, src_g, src_b, src_a = source
    dst_r, dst_g, dst_b, dst_a = target
    result = image.copy()
    pixels = result.load()
    w, h = result.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if (
                abs(r - src_r) <= tolerance
                and abs(g - src_g) <= tolerance
                and abs(b - src_b) <= tolerance
                and abs(a - src_a) <= tolerance
            ):
                pixels[x, y] = (dst_r, dst_g, dst_b, dst_a)
    return result


def draw_brush(image: Image.Image, x: int, y: int, color: tuple[int, int, int, int], size: int = 1) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    result = image.copy()
    draw = ImageDraw.Draw(result)
    half = max(0, size // 2)
    left = max(0, x - half)
    top = max(0, y - half)
    right = min(result.width - 1, x + half)
    bottom = min(result.height - 1, y + half)
    draw.rectangle([left, top, right, bottom], fill=color)
    return result


def draw_line(
    image: Image.Image,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    size: int = 1,
) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    result = image.copy()
    draw = ImageDraw.Draw(result)
    draw.line([start, end], fill=color, width=max(1, size))
    return result


def flood_fill(
    image: Image.Image,
    x: int,
    y: int,
    color: tuple[int, int, int, int],
    tolerance: int = 0,
) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    result = image.copy()
    try:
        ImageDraw.floodfill(result, (x, y), color, thresh=tolerance)
        return result
    except Exception:
        pass

    pixels = result.load()
    w, h = result.size
    target = pixels[x, y]
    if target == color:
        return result

    def within(px):
        return all(abs(px[i] - target[i]) <= tolerance for i in range(4))

    queue = deque([(x, y)])
    visited = set()
    while queue:
        cx, cy = queue.popleft()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            continue
        if not within(pixels[cx, cy]):
            continue
        pixels[cx, cy] = color
        queue.extend([(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)])
    return result


def adjust_alpha(image: Image.Image, scale: float = 1.0, offset: int = 0) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    result = image.copy()
    pixels = result.load()
    w, h = result.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            new_a = int(a * scale + offset)
            new_a = max(0, min(255, new_a))
            pixels[x, y] = (r, g, b, new_a)
    return result


def clamp_alpha(
    image: Image.Image,
    low_threshold: int,
    low_value: int,
    high_threshold: int,
    high_value: int,
) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    result = image.copy()
    pixels = result.load()
    w, h = result.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a <= low_threshold:
                pixels[x, y] = (r, g, b, low_value)
            elif a >= high_threshold:
                pixels[x, y] = (r, g, b, high_value)
    return result


def _block_color(pixels, bx, by, block, method: str) -> tuple[int, int, int, int]:
    colors = []
    for y in range(by, by + block):
        for x in range(bx, bx + block):
            colors.append(pixels[x, y])
    if method == "Average":
        r = int(sum(c[0] for c in colors) / len(colors))
        g = int(sum(c[1] for c in colors) / len(colors))
        b = int(sum(c[2] for c in colors) / len(colors))
        a = int(sum(c[3] for c in colors) / len(colors))
        return (r, g, b, a)
    counts = Counter(colors)
    return counts.most_common(1)[0][0]


def merge_squares(
    image: Image.Image,
    block: int,
    method: str = "Dominant",
    preserve_size: bool = True,
) -> Image.Image:
    if block <= 1:
        return image.copy()
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    w, h = image.size
    new_w = w // block
    new_h = h // block
    if new_w == 0 or new_h == 0:
        return image.copy()

    src = image
    spx = src.load()
    down = Image.new("RGBA", (new_w, new_h))
    dpx = down.load()

    for by in range(new_h):
        for bx in range(new_w):
            color = _block_color(spx, bx * block, by * block, block, method)
            dpx[bx, by] = color

    if preserve_size:
        return down.resize((new_w * block, new_h * block), Image.Resampling.NEAREST)
    return down


def split_squares(image: Image.Image, block: int) -> Image.Image:
    if block <= 1:
        return image.copy()
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    return image.resize((w * block, h * block), Image.Resampling.NEAREST)

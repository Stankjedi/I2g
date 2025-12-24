from PIL import Image


def pixel_perfect_outline(image: Image.Image, passes: int = 1) -> Image.Image:
    """Remove diagonal-only pixels to reduce jagged outline artifacts."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    result = image.copy()
    w, h = result.size
    neighbors_diag = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    neighbors_orth = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    for _ in range(max(1, passes)):
        src = result
        dst = src.copy()
        spx = src.load()
        dpx = dst.load()

        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if spx[x, y][3] == 0:
                    continue
                orth_count = 0
                diag_count = 0
                for dx, dy in neighbors_orth:
                    if spx[x + dx, y + dy][3] > 0:
                        orth_count += 1
                for dx, dy in neighbors_diag:
                    if spx[x + dx, y + dy][3] > 0:
                        diag_count += 1
                if orth_count == 0 and diag_count >= 2:
                    dpx[x, y] = (0, 0, 0, 0)

        result = dst

    return result

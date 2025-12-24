from PIL import Image


RESAMPLE_MAP = {
    "Nearest": Image.Resampling.NEAREST,
    "Bilinear": Image.Resampling.BILINEAR,
    "Bicubic": Image.Resampling.BICUBIC,
}


def resize_image(image: Image.Image, scale: float, method: str) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    resample = RESAMPLE_MAP.get(method, Image.Resampling.NEAREST)
    w, h = image.size
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return image.resize((new_w, new_h), resample=resample)

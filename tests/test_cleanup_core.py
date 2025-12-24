import pytest
from PIL import Image

from gui.cleanup_core import CancelledError, cleanup_background


def make_outlined_image(
    size=(16, 16),
    bg=(0, 255, 0, 255),
    outline=(0, 0, 0, 255),
    interior=(255, 0, 0, 255),
) -> Image.Image:
    img = Image.new("RGBA", size, bg)
    px = img.load()
    left, top, right, bottom = 4, 4, size[0] - 5, size[1] - 5
    for x in range(left, right + 1):
        px[x, top] = outline
        px[x, bottom] = outline
    for y in range(top, bottom + 1):
        px[left, y] = outline
        px[right, y] = outline
    for y in range(top + 1, bottom):
        for x in range(left + 1, right):
            px[x, y] = interior
    return img


def test_cleanup_transparent_background_preserves_outline_and_interior():
    img = make_outlined_image()

    out, stats = cleanup_background(
        img,
        outline_threshold=20,
        fill_tolerance=80,
        dilation_passes=10,
    )

    out_px = out.load()

    # Background corners become transparent
    assert out_px[0, 0][3] == 0
    assert out_px[out.width - 1, 0][3] == 0
    assert out_px[0, out.height - 1][3] == 0
    assert out_px[out.width - 1, out.height - 1][3] == 0

    # Outline pixels remain opaque and dark
    left, top = 4, 4
    outline_px = out_px[left, top]
    assert outline_px[3] == 255
    assert outline_px[:3] == (0, 0, 0)

    # Interior pixels remain opaque and preserve RGB
    interior_px = out_px[left + 1, top + 1]
    assert interior_px[3] == 255
    assert interior_px[:3] == (255, 0, 0)

    # Sanity: algo removed something
    assert stats["pixels_removed"] > 0


def test_cleanup_is_deterministic():
    img = make_outlined_image()

    out1, _ = cleanup_background(
        img,
        outline_threshold=20,
        fill_tolerance=80,
        dilation_passes=10,
    )
    out2, _ = cleanup_background(
        img,
        outline_threshold=20,
        fill_tolerance=80,
        dilation_passes=10,
    )

    assert out1.tobytes() == out2.tobytes()


def test_stats_schema_and_ranges():
    img = make_outlined_image()
    _, stats = cleanup_background(img, outline_threshold=20, fill_tolerance=80, dilation_passes=10)

    for key in ("pixels_removed", "removal_percentage", "processing_time_ms", "image_width", "image_height"):
        assert key in stats

    assert 0 <= stats["removal_percentage"] <= 100
    assert stats["processing_time_ms"] >= 0


def test_cleanup_can_cancel_early():
    img = make_outlined_image()
    with pytest.raises(CancelledError):
        cleanup_background(
            img,
            outline_threshold=20,
            fill_tolerance=80,
            dilation_passes=10,
            cancel_check=lambda: True,
        )


def test_dilation_passes_monotonic_and_preserves_content():
    img = make_outlined_image()
    img.putpixel((1, 1), (255, 0, 255, 199))  # bg-like remnant that flood fill should not remove

    out0, stats0 = cleanup_background(img, outline_threshold=20, fill_tolerance=80, dilation_passes=0)
    out5, stats5 = cleanup_background(img, outline_threshold=20, fill_tolerance=80, dilation_passes=5)

    assert out0.getpixel((1, 1))[3] != 0
    assert out5.getpixel((1, 1))[3] == 0
    assert stats0["pixels_removed"] < stats5["pixels_removed"]

    for out in (out0, out5):
        assert out.getpixel((4, 4)) == (0, 0, 0, 255)
        assert out.getpixel((5, 5)) == (255, 0, 0, 255)

from pathlib import Path

from PIL import Image

from gui import cleanup_cli


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


def test_cli_batch_processing_creates_png_outputs(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()

    make_outlined_image(interior=(255, 0, 0, 255)).save(input_dir / "a.png")
    make_outlined_image(interior=(0, 0, 255, 255)).save(input_dir / "b.png")

    exit_code = cleanup_cli.main(
        [
            "--input",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--threshold",
            "20",
            "--dilation",
            "10",
        ]
    )
    assert exit_code == 0

    out_a = output_dir / "a_cleaned.png"
    out_b = output_dir / "b_cleaned.png"
    assert out_a.exists()
    assert out_b.exists()

    img_a = Image.open(out_a)
    assert img_a.format == "PNG"
    assert img_a.mode == "RGBA"
    assert img_a.getpixel((0, 0))[3] == 0


def test_cli_recursive_processing_preserves_structure(tmp_path: Path):
    input_dir = tmp_path / "in"
    nested_dir = input_dir / "nested"
    output_dir = tmp_path / "out"
    nested_dir.mkdir(parents=True)

    make_outlined_image(interior=(255, 0, 0, 255)).save(nested_dir / "c.png")

    exit_code = cleanup_cli.main(
        [
            "--input",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--recursive",
            "--threshold",
            "20",
            "--dilation",
            "10",
        ]
    )
    assert exit_code == 0

    out_c = output_dir / "nested" / "c_cleaned.png"
    assert out_c.exists()


def test_cli_nonexistent_input_returns_nonzero(tmp_path: Path):
    output_dir = tmp_path / "out"
    exit_code = cleanup_cli.main(
        [
            "--input",
            str(tmp_path / "does-not-exist"),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert exit_code != 0

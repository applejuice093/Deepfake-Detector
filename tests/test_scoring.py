"""Unit tests for score conversion and risk banding (no model needed)."""
import pytest

import main


@pytest.mark.parametrize(
    "prob,expected",
    [(0.0, 0), (0.5999, 60), (0.294, 29), (0.295, 30), (1.0, 100), (1.0000001, 100), (-1e-9, 0)],
)
def test_to_percent_rounds_and_clamps(prob, expected):
    assert main._to_percent(prob) == expected


def test_transparent_pixels_become_white_not_black():
    from PIL import Image

    img = Image.new("RGBA", (2, 1), (0, 0, 0, 0))  # fully transparent
    img.putpixel((1, 0), (255, 0, 0, 255))  # one opaque red pixel
    rgb = main._to_rgb(img)
    assert rgb.mode == "RGB"
    assert rgb.getpixel((0, 0)) == (255, 255, 255)
    assert rgb.getpixel((1, 0)) == (255, 0, 0)


def test_palette_transparency_is_composited():
    from PIL import Image

    img = Image.new("P", (1, 1), 0)
    img.putpalette([0, 0, 0] * 256)
    img.info["transparency"] = 0
    assert main._to_rgb(img).getpixel((0, 0)) == (255, 255, 255)


def test_grayscale_is_converted_to_rgb():
    from PIL import Image

    rgb = main._to_rgb(Image.new("L", (1, 1), 128))
    assert rgb.getpixel((0, 0)) == (128, 128, 128)

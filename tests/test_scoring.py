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


@pytest.mark.parametrize("mode,value,expected", [("I;16", 32896, 128), ("I", 65535, 255), ("F", 0.5, 128)])
def test_high_bit_depth_grayscale_is_rescaled_not_clipped(mode, value, expected):
    from PIL import Image

    rgb = main._to_rgb(Image.new(mode, (1, 1), value))
    assert rgb.mode == "RGB"
    assert rgb.getpixel((0, 0)) == (expected,) * 3


def test_16_bit_png_upload_is_not_washed_out(monkeypatch):
    import io

    from fastapi.testclient import TestClient
    from PIL import Image

    seen = {}

    def capture(image_np):
        seen["px"] = image_np[0, 0].tolist()
        return 5

    monkeypatch.setattr(main, "deepfake_score", capture)
    buf = io.BytesIO()
    Image.new("I;16", (4, 4), 1028).save(buf, format="PNG")  # 1028/257 = 4
    res = TestClient(main.app).post("/analyze", files={"file": ("g.png", buf.getvalue(), "image/png")})
    assert res.status_code == 200
    assert seen["px"] == [4, 4, 4]

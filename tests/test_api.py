"""API tests. The ML model is stubbed out, so these run without torch,
transformers or network access."""
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "deepfake_score", lambda image_np: 75)
    return TestClient(main.app)


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    "score,expected",
    [(0, "Low"), (29, "Low"), (30, "Medium"), (59, "Medium"), (60, "High"), (100, "High")],
)
def test_classify_risk_bands(score, expected):
    assert main.classify_risk(score).startswith(expected)


def test_health(client, monkeypatch):
    monkeypatch.setattr(main, "_model", None)
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "model": main.MODEL_NAME, "model_loaded": False}


def test_health_reports_loaded_model(client, monkeypatch):
    monkeypatch.setattr(main, "_model", object())
    assert client.get("/api/health").json()["model_loaded"] is True


def test_analyze_image_returns_score(client):
    res = client.post("/analyze", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert res.status_code == 200
    body = res.json()
    assert body["overall_score"] == 75
    assert body["risk_level"].startswith("High")


def test_uploads_are_never_written_to_disk(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = client.post("/analyze", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert res.status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_rejects_non_image(client):
    res = client.post("/analyze", files={"file": ("v.mp4", b"\x00\x01", "video/mp4")})
    assert res.status_code == 415


def test_rejects_corrupt_image(client):
    res = client.post("/analyze", files={"file": ("x.png", b"not an image", "image/png")})
    assert res.status_code == 400


def test_rejects_empty_file(client):
    res = client.post("/analyze", files={"file": ("x.png", b"", "image/png")})
    assert res.status_code == 400


def test_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    res = client.post("/analyze", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert res.status_code == 413


def test_path_traversal_filename_is_ignored(client):
    res = client.post(
        "/analyze", files={"file": ("../../evil.png", _png_bytes(), "image/png")}
    )
    assert res.status_code == 200
    assert not os.path.exists(os.path.join("..", "evil.png"))


def test_rejects_images_with_too_many_pixels(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_IMAGE_PIXELS", 50)  # 8x8 = 64 px > 50
    res = client.post("/analyze", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert res.status_code == 413
    assert "too large" in res.json()["detail"]


def test_model_failure_returns_503(monkeypatch):
    def broken(image_np):
        raise OSError("could not download weights")

    monkeypatch.setattr(main, "deepfake_score", broken)
    res = TestClient(main.app).post(
        "/analyze", files={"file": ("a.png", _png_bytes(), "image/png")}
    )
    assert res.status_code == 503
    assert "weights" not in res.json()["detail"]  # internals are not leaked


def test_exif_orientation_is_applied_before_inference(monkeypatch):
    seen = {}

    def capture(image_np):
        seen["shape"] = image_np.shape
        return 10

    monkeypatch.setattr(main, "deepfake_score", capture)

    # 8 wide x 4 tall, tagged "rotate 90 CW" (EXIF orientation 6) like a
    # portrait phone photo; upright it is 4 wide x 8 tall.
    img = Image.new("RGB", (8, 4), "blue")
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())

    res = TestClient(main.app).post(
        "/analyze", files={"file": ("p.jpg", buf.getvalue(), "image/jpeg")}
    )
    assert res.status_code == 200
    assert seen["shape"] == (8, 4, 3)  # (height, width, channels)


@pytest.mark.parametrize("fmt,mime", [("WEBP", "image/webp"), ("GIF", "image/gif"), ("BMP", "image/bmp")])
def test_accepts_common_formats(client, fmt, mime):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, format=fmt)
    res = client.post("/analyze", files={"file": ("a", buf.getvalue(), mime)})
    assert res.status_code == 200


def test_rejects_formats_outside_the_allowlist(client):
    # A valid ICO file is decodable by Pillow but is not an allowed format,
    # even when the client claims it is a PNG.
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buf, format="ICO")
    res = client.post("/analyze", files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert res.status_code == 400
    assert "Supported formats" in res.json()["detail"]

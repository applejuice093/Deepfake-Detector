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


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


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

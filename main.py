from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import io
import logging
import os
import threading
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("deepfake_detector")


def _env_int(name, default):
    """Read a positive integer from the environment, falling back to
    `default` (with a warning) instead of crashing at import time on typos
    like MAX_UPLOAD_MB=10mb."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning("Ignoring invalid %s=%r; using default %s", name, raw, default)
        return default
    return value


def _cors_origins():
    """Comma-separated CORS_ORIGINS, e.g. "https://a.com,https://b.com".
    Defaults to "*" (any origin), matching the previous behaviour."""
    raw = os.getenv("CORS_ORIGINS", "*")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"]


# -------------------------
# App setup
# -------------------------

app = FastAPI(title="Deepfake Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_MB", 10) * 1024 * 1024
# Highly compressible images can be tiny on the wire but expand to gigabytes
# once decoded ("decompression bombs"). 40 MP comfortably covers phone photos.
MAX_IMAGE_PIXELS = _env_int("MAX_IMAGE_MEGAPIXELS", 40) * 1_000_000

# -------------------------
# HuggingFace model (loaded lazily on first request)
# -------------------------

MODEL_NAME = os.getenv("MODEL_NAME", "prithivMLmods/deepfake-detector-model-v1")

_processor = None
_model = None
_fake_label_index = None
_model_lock = threading.Lock()


def _load_model():
    """Load the model once. Deferred so the app starts fast and tests can
    run without downloading weights."""
    global _processor, _model, _fake_label_index
    if _model is not None:
        return _processor, _model, _fake_label_index
    # Inference runs in a thread pool, so concurrent first requests could
    # otherwise each download/load the weights. Double-checked locking makes
    # the load happen exactly once.
    with _model_lock:
        if _model is None:
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
            model = AutoModelForImageClassification.from_pretrained(MODEL_NAME)
            model.eval()
            # The model's labels are {0: "Fake", 1: "Real"}; look the index up
            # from the config instead of hardcoding it so the score is P(fake).
            fake_idx = next(
                int(i) for i, label in model.config.id2label.items()
                if label.lower() == "fake"
            )
            # Publish the model last so other threads never see a half-set state.
            _processor, _fake_label_index = processor, fake_idx
            _model = model
    return _processor, _model, _fake_label_index

# -------------------------
# Inference
# -------------------------

def _to_percent(probability):
    """Convert a 0-1 probability to an integer percentage.

    Rounds to the nearest integer (int() would truncate, so a 0.5999
    probability showed as 59 and fell into the Medium band instead of
    High) and clamps to 0-100 to absorb float noise."""
    return max(0, min(100, int(round(float(probability) * 100))))


def deepfake_score(image_np):
    """Return the probability (0-100) that the image is a deepfake."""
    import torch

    processor, model, fake_idx = _load_model()
    inputs = processor(images=image_np, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)
    return _to_percent(probs[0][fake_idx].item())

def classify_risk(score):
    """Map a 0-100 deepfake probability to a human-readable risk band."""
    if score < 30:
        return "Low (Likely Real)"
    if score < 60:
        return "Medium (Inconclusive)"
    return "High (Possible Deepfake)"

def _to_rgb(img):
    """Convert any Pillow image to RGB for the model.

    A plain .convert("RGB") drops the alpha channel, which turns the
    transparent areas of PNG/WebP/GIF images black and gives the model a
    picture the user never saw. Composite transparent images onto white
    first, the way browsers display them."""
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA", "PA"):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return img.convert("RGB")


# -------------------------
# API
# -------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image files are supported")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Decode straight from memory: user images never touch the disk, so there
    # is nothing to clean up and no filename/path handling to get wrong.
    try:
        with Image.open(io.BytesIO(data)) as img:
            # Image.open only parses the header, so the size check is cheap
            # and happens before any pixel data is decoded.
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=413,
                    detail=f"Image dimensions too large ({width}x{height}); "
                    f"max {MAX_IMAGE_PIXELS // 1_000_000} megapixels",
                )
            # Phone cameras store rotation in EXIF instead of rotating pixels;
            # apply it so the model sees the photo upright, as the user does.
            upright = ImageOps.exif_transpose(img)
            img_np = np.array(_to_rgb(upright))
    except Image.DecompressionBombError:
        raise HTTPException(status_code=413, detail="Image dimensions too large")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="File is not a valid image")

    # Model inference is CPU-bound and synchronous; run it in the thread pool so
    # it does not block the event loop (health checks, other uploads) meanwhile.
    try:
        score = await run_in_threadpool(deepfake_score, img_np)
    except Exception:
        # Typically the weights could not be downloaded/loaded (no network,
        # bad MODEL_NAME) or the model failed on this input. Log the details
        # server-side and give the client a clear, non-leaky message.
        logger.exception("Deepfake inference failed (model=%s)", MODEL_NAME)
        raise HTTPException(
            status_code=503,
            detail="The detection model is unavailable right now. Please try again later.",
        )

    risk_level = classify_risk(score)

    return {
        "media_type": "Image",
        "overall_score": score,
        "risk_level": risk_level,
        "indicators": [
            {
                "name": "AI Model Confidence",
                "score": score,
                "description": "Pretrained Hugging Face deepfake detection model"
            }
        ],
        "explanation": (
            "This result is probabilistic and based on a pretrained "
            "deepfake detection model. It is not definitive proof."
        )
    }

# -------------------------
# Serve your WEBSITE UI
# -------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

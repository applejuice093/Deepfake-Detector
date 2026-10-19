from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import io
import os
import numpy as np
from PIL import Image, UnidentifiedImageError

# -------------------------
# App setup
# -------------------------

app = FastAPI(title="Deepfake Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024

# -------------------------
# HuggingFace model (loaded lazily on first request)
# -------------------------

MODEL_NAME = os.getenv("MODEL_NAME", "prithivMLmods/deepfake-detector-model-v1")

_processor = None
_model = None
_fake_label_index = None


def _load_model():
    """Load the model once. Deferred so the app starts fast and tests can
    run without downloading weights."""
    global _processor, _model, _fake_label_index
    if _model is None:
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        _processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
        _model = AutoModelForImageClassification.from_pretrained(MODEL_NAME)
        _model.eval()
        # The model's labels are {0: "Fake", 1: "Real"}; look the index up
        # from the config instead of hardcoding it so the score is P(fake).
        _fake_label_index = next(
            int(i) for i, label in _model.config.id2label.items()
            if label.lower() == "fake"
        )
    return _processor, _model, _fake_label_index

# -------------------------
# Inference
# -------------------------

def deepfake_score(image_np):
    """Return the probability (0-100) that the image is a deepfake."""
    import torch

    processor, model, fake_idx = _load_model()
    inputs = processor(images=image_np, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)
    return int(probs[0][fake_idx].item() * 100)

def classify_risk(score):
    """Map a 0-100 deepfake probability to a human-readable risk band."""
    if score < 30:
        return "Low (Likely Real)"
    if score < 60:
        return "Medium (Inconclusive)"
    return "High (Possible Deepfake)"

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
            img_np = np.array(img.convert("RGB"))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="File is not a valid image")

    score = deepfake_score(img_np)

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

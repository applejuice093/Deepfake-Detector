from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import os
import uuid
import torch
import numpy as np
from PIL import Image, UnidentifiedImageError

from transformers import AutoImageProcessor, AutoModelForImageClassification

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

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024

# -------------------------
# Load OLD HuggingFace model
# -------------------------

MODEL_NAME = "prithivMLmods/deepfake-detector-model-v1"

processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
model = AutoModelForImageClassification.from_pretrained(MODEL_NAME)
model.eval()

# The model's labels are {0: "Fake", 1: "Real"}; look the index up from the
# config instead of hardcoding it so the score is always P(fake).
FAKE_LABEL_INDEX = next(
    int(i) for i, label in model.config.id2label.items() if label.lower() == "fake"
)

# -------------------------
# Inference
# -------------------------

def deepfake_score(image_np):
    inputs = processor(images=image_np, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)
    return int(probs[0][FAKE_LABEL_INDEX].item() * 100)

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

    # Never trust the client filename (path traversal / overwrites).
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ""
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    with open(file_path, "wb") as buffer:
        buffer.write(data)

    try:
        with Image.open(file_path) as img:
            img_np = np.array(img.convert("RGB"))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="File is not a valid image")
    finally:
        # Uploads are only needed for inference; do not keep user images.
        if os.path.exists(file_path):
            os.remove(file_path)

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

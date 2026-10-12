from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import os
import shutil
import torch
import numpy as np
from PIL import Image

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

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    img = Image.open(file_path).convert("RGB")
    img_np = np.array(img)

    score = deepfake_score(img_np)

    risk_level = (
        "Low (Likely Real)" if score < 30 else
        "Medium (Inconclusive)" if score < 60 else
        "High (Possible Deepfake)"
    )

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

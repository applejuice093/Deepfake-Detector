FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Model weights are cached here on first use; must be writable by the app user.
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Install the CPU-only PyTorch wheel first: the default wheel bundles CUDA
# libraries (several GB) that this CPU inference server never uses.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# Run as an unprivileged user (UID 1000 also matches Hugging Face Spaces).
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
RUN mkdir -p "$HF_HOME" && chown -R app:app /app
USER app

# Listen on $PORT when the host sets one (Hugging Face Spaces uses 7860,
# many PaaS hosts inject their own); default to 8000.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)" || exit 1

# Shell form so $PORT is expanded; exec keeps uvicorn as PID 1 for signals.
CMD exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"

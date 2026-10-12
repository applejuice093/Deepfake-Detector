PYTHON ?= python3

.PHONY: install install-dev run test docker-build docker-run clean

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

run:
	uvicorn main:app --reload --port 8000

test:
	$(PYTHON) -m pytest -q

docker-build:
	docker build -t deepfake-detector .

docker-run:
	docker run --rm -p 8000:8000 deepfake-detector

clean:
	rm -rf .pytest_cache __pycache__ tests/__pycache__

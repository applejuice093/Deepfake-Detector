"""Tests for lazy model loading, using a fake `transformers` module so no
weights are downloaded."""
import sys
import threading
import time
import types

import pytest

import main


class _FakeConfig:
    id2label = {"0": "Fake", "1": "Real"}


class _FakeModel:
    config = _FakeConfig()

    def eval(self):
        return self


@pytest.fixture
def fake_transformers(monkeypatch):
    calls = {"processor": 0, "model": 0}

    class AutoImageProcessor:
        @staticmethod
        def from_pretrained(name):
            calls["processor"] += 1
            return object()

    class AutoModelForImageClassification:
        @staticmethod
        def from_pretrained(name):
            calls["model"] += 1
            time.sleep(0.05)  # widen the race window
            return _FakeModel()

    module = types.SimpleNamespace(
        AutoImageProcessor=AutoImageProcessor,
        AutoModelForImageClassification=AutoModelForImageClassification,
    )
    monkeypatch.setitem(sys.modules, "transformers", module)
    monkeypatch.setattr(main, "_processor", None)
    monkeypatch.setattr(main, "_model", None)
    monkeypatch.setattr(main, "_fake_label_index", None)
    return calls


def test_fake_label_index_comes_from_config(fake_transformers):
    _, _, fake_idx = main._load_model()
    assert fake_idx == 0


def test_model_is_loaded_once_under_concurrency(fake_transformers):
    threads = [threading.Thread(target=main._load_model) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake_transformers == {"processor": 1, "model": 1}

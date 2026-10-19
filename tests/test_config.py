import pytest

import main


@pytest.mark.parametrize(
    "raw,expected",
    [(None, 10), ("", 10), ("25", 25), ("10mb", 10), ("0", 10), ("-5", 10)],
)
def test_env_int_falls_back_on_invalid_values(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("SOME_LIMIT", raising=False)
    else:
        monkeypatch.setenv("SOME_LIMIT", raw)
    assert main._env_int("SOME_LIMIT", 10) == expected


def test_cors_origins_default_and_list(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert main._cors_origins() == ["*"]
    monkeypatch.setenv("CORS_ORIGINS", " https://a.com, https://b.com ,")
    assert main._cors_origins() == ["https://a.com", "https://b.com"]
    monkeypatch.setenv("CORS_ORIGINS", " , ")
    assert main._cors_origins() == ["*"]

from app.core.config import get_env_file
import os
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def restore_env(monkeypatch):
    # Save and restore APP_ENV after each test
    original = os.environ.get("APP_ENV")

    yield

    if original is not None:
        os.environ["APP_ENV"] = original
    else:
        os.environ.pop("APP_ENV", None)

def test_get_env_file_default(monkeypatch):
    # Unset APP_ENV to test default
    monkeypatch.delenv("APP_ENV", raising=False)
    env_file = get_env_file()

    assert env_file.endswith(".envs/dev/backend.env")

def test_get_env_file_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    env_file = get_env_file()

    assert env_file.endswith(".envs/dev/backend.env")

def test_get_env_file_dev_docker(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev_docker")
    env_file = get_env_file()

    assert env_file.endswith(".envs/dev_docker/backend.env")

def test_get_env_file_prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    env_file = get_env_file()

    assert env_file.endswith(".envs/prod/backend.env")

def test_get_env_file_example_raises(monkeypatch):
    # Patch Path to simulate .example file
    class DummyPath(Path):
        @property
        def name(self):
            return "backend.env.example"
        def __truediv__(self, key):
            return self
        def __str__(self):
            return "/fake/path/.envs/dev/backend.env.example"

    monkeypatch.setattr("app.core.config.Path", DummyPath)

    with pytest.raises(FileNotFoundError):
        get_env_file()

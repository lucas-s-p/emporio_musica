from pathlib import Path

import pytest

from emporio.data import Store, load_store

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def store() -> Store:
    return load_store(DATA_DIR)
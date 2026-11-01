import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def store(tmp_path):
    from reelforge.storage import ProjectStore

    return ProjectStore(tmp_path / "projects")


@pytest.fixture()
def project(store):
    from reelforge.models import ProjectSettings

    return store.create(ProjectSettings(topic="Test topic", duration=45), pid="test-topic")

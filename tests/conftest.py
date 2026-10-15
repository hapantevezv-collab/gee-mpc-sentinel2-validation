from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "acceptance" / "demo"


@pytest.fixture(scope="session")
def demo_dir() -> Path:
    return DEMO


@pytest.fixture(scope="session")
def demo_aoi() -> Path:
    return ROOT / "data" / "demo_aoi.geojson"

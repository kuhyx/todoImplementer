import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asksfakes import Rig


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)

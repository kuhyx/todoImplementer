"""Makes board_helpers importable (the repo runs pytest with --import-mode=importlib)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

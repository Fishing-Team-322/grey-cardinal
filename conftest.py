from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHONPATHS = [
    ROOT / "packages" / "contracts" / "python",
    ROOT / "apps" / "audio-worker" / "src",
    ROOT / "apps" / "brain-api" / "src",
    ROOT / "apps" / "telegram-bot" / "src",
]

for path in PYTHONPATHS:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

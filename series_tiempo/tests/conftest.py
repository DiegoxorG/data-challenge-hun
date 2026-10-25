"""Permite `import series_tiempo`, `import Cuellos_botella` y `import hun` desde cualquier carpeta."""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(1, str(_REPO / "src"))

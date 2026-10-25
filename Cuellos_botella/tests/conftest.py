"""Permite `import Cuellos_botella` (y `import hun`, aunque no esté instalado con pip -e)
al correr pytest desde cualquier carpeta."""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(1, str(_REPO / "src"))

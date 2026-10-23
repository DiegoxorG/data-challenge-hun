"""Permite `import Cuellos_botella` al correr pytest desde cualquier carpeta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

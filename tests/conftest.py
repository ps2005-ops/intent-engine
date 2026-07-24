"""Make test-local helper modules (recorded fixtures) importable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

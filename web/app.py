"""Streamlit Cloud entry-point shim.

The Cloud app is configured to run ``web/app.py``; keep that deployment
working by delegating to the canonical root entry point.
"""

import sys
from pathlib import Path
import runpy


_ROOT_ENTRY = Path(__file__).resolve().parent.parent / "streamlit_app.py"

# Streamlit Cloud runs this shim from web/, which puts web/ on sys.path but
# not the repo root. Add the root so `import src.*` behaves like the root
# entry point.
sys.path.insert(0, str(_ROOT_ENTRY.parent))

runpy.run_path(str(_ROOT_ENTRY), run_name="__main__")

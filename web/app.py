"""Streamlit Cloud entry-point shim.

The Cloud app is configured to run ``web/app.py``; keep that deployment
working by delegating to the canonical root entry point.
"""

from pathlib import Path
import runpy


_ROOT_ENTRY = Path(__file__).resolve().parent.parent / "streamlit_app.py"
runpy.run_path(str(_ROOT_ENTRY), run_name="__main__")

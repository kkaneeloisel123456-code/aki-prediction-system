"""
AKI Prediction System — Streamlit Cloud Entry Point

This file lives at the repository root so Streamlit Cloud can find it.
It delegates to web/app.py with correct __file__ path resolution.
"""
from pathlib import Path

# Set __file__ to web/app.py so Path(__file__).parent.parent resolves to project root
_web_app = Path(__file__).parent / 'web' / 'app.py'
__file__ = str(_web_app)

# Execute the real web app
with open(_web_app, encoding='utf-8') as _f:
    exec(compile(_f.read(), str(_web_app), 'exec'))

import sys
from pathlib import Path

# backend/ itself needs to be on sys.path for the app's own import style
# (`from config import ...`, `from services import accounts`, ...) — this
# is how uvicorn runs it too (`cd backend && uvicorn app:app`). Without
# this, pytest's default "prepend" import mode only puts backend/tests/ on
# sys.path, not backend/ itself.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
from pathlib import Path

DB = os.environ.get("BL_DB", str(Path(__file__).parent / "brandlens2.db"))
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("BL_MODEL", "claude-sonnet-5-5")
SECRET = os.environ.get("BL_SECRET", "change-me").encode()

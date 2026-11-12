"""Settings read once at import time from environment variables (and a local `.env` file)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("landmark")

ROOT = Path(__file__).resolve().parent.parent


def _list(name, default):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# Models listed as "Free of charge" on the Gemini API free tier (https://ai.google.dev/gemini-api/docs/pricing).
# Anything else in GEMINI_MODELS is dropped, so a typo or a paid model can never be called.
FREE_GEMINI_MODELS = frozenset(
    {
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
    }
)

MODEL_PATH = Path(os.getenv("LANDMARK_MODEL_PATH", ROOT / "models" / "landmarks_classifier_europe_v1.tflite"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
_requested_models = _list("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite")
GEMINI_MODELS = [m for m in _requested_models if m in FREE_GEMINI_MODELS]
REJECTED_GEMINI_MODELS = [m for m in _requested_models if m not in FREE_GEMINI_MODELS]
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "15"))

VERIFY_MIN_SCORE = float(os.getenv("VERIFY_MIN_SCORE", "0.85"))
VERIFY_MIN_MARGIN = float(os.getenv("VERIFY_MIN_MARGIN", "0.05"))
VERIFY_SURE_SCORE = float(os.getenv("VERIFY_SURE_SCORE", "0.95"))
GEMINI_CANDIDATES = 5

# Vercel rejects request bodies above 4.5 MB before they reach the app.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(4 * 1024 * 1024)))
MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_DOWNLOAD_BYTES", str(15 * 1024 * 1024)))
DOWNLOAD_TIMEOUT_S = float(os.getenv("DOWNLOAD_TIMEOUT_S", "10"))

INFO_LANGUAGE = os.getenv("INFO_LANGUAGE", "bg")
WIKIPEDIA_TIMEOUT_S = float(os.getenv("WIKIPEDIA_TIMEOUT_S", "8"))

API_KEYS = frozenset(_list("API_KEYS", ""))
CORS_ALLOW_ORIGINS = _list("CORS_ALLOW_ORIGINS", "*")

USER_AGENT = "AI-Landmark-Recognition/1.0 (+https://github.com/jivko25/AI-Landmark-Recognition)"

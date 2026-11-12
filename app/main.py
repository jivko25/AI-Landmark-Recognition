"""AI Landmark Recognition API (FastAPI). Vercel picks up `app` from this file automatically.

Local run:  uvicorn app.main:app --reload
Docs:       http://localhost:8000/docs
"""

import re
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app import config
from app.images import ImageError, download_image, open_image, unwrap_image_url
from app.pipeline import Services, analyze
from app.recognizer import LandmarkRecognizer
from app.schemas import HealthResponse, PredictResponse, VerifyMode
from app.verifier import GeminiVerifier
from app.wiki import WikipediaClient


def build_services():
    if config.REJECTED_GEMINI_MODELS:
        config.log.warning("Ignoring non-free Gemini models: %s", ", ".join(config.REJECTED_GEMINI_MODELS))
    verifier = None
    if config.GEMINI_API_KEY and config.GEMINI_MODELS:
        verifier = GeminiVerifier(config.GEMINI_API_KEY, config.GEMINI_MODELS, config.GEMINI_TIMEOUT_S)
    return Services(
        recognizer=LandmarkRecognizer(config.MODEL_PATH),
        verifier=verifier,
        wiki=WikipediaClient(),
    )


_services_lock = threading.Lock()


def get_services(app):
    if getattr(app.state, "services", None) is None:
        with _services_lock:
            if getattr(app.state, "services", None) is None:
                app.state.services = build_services()
    return app.state.services


@asynccontextmanager
async def lifespan(app):
    get_services(app)
    yield


DESCRIPTION = """
Разпознава европейски забележителности по снимка и връща информация за тях.

* Локален модел: **Google Landmarks (Europe)** от Kaggle, около 33 500 забележителности.
* Когато локалният модел не е сигурен, **Gemini** (само безплатни модели) проверява и при нужда поправя отговора.
* Информацията за забележителността идва от **Wikipedia**.

Изпрати снимка като файл (`file`) или като URL (`url`).
"""

app = FastAPI(title="AI Landmark Recognition", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ALLOW_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Нужен само ако е зададен API_KEYS")


def require_api_key(key: str | None = Security(api_key_header)):
    if config.API_KEYS and key not in config.API_KEYS:
        raise HTTPException(401, "Липсва или е грешен X-API-Key")


@app.exception_handler(ImageError)
def image_error_handler(request, exc: ImageError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


LANG_RE = re.compile(r"^[a-z]{2,3}$")
VERIFY_HELP = "auto = Gemini само при несигурен резултат, always = винаги, never = никога"
LANG_HELP = "Език на информацията от Wikipedia (bg, en, de, ...). Ако няма статия на този език, връща английската."


def check_lang(lang):
    if not LANG_RE.match(lang):
        raise HTTPException(400, "lang трябва да е код на език, например bg или en")
    return lang


@app.get("/", include_in_schema=False)
def root():
    return {"name": "AI Landmark Recognition", "docs": "/docs", "health": "/health", "predict": "/predict"}


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request):
    services = get_services(request.app)
    return HealthResponse(
        status="ok",
        model_loaded=services.recognizer is not None,
        landmarks_known=services.recognizer.landmarks_known,
        gemini_enabled=services.verifier is not None,
        gemini_models=services.verifier.models if services.verifier else [],
    )


@app.post("/predict", response_model=PredictResponse, tags=["landmarks"], dependencies=[Depends(require_api_key)])
def predict(
    request: Request,
    file: UploadFile | None = File(None, description="Снимка (jpg, png, webp, ...), до 4 MB"),
    url: str | None = Form(None, description="Или URL към снимка (може и като ?url=... в адреса)"),
    top: int = Form(3, ge=1, le=20, description="Колко кандидата да се върнат"),
    verify: VerifyMode = Form("auto", description=VERIFY_HELP),
    lang: str = Form(config.INFO_LANGUAGE, description=LANG_HELP),
):
    """Разпознава забележителност от прикачена снимка или от URL."""
    query = request.query_params
    verify = query.get("verify", verify)
    if verify not in ("auto", "always", "never"):
        raise HTTPException(400, "verify трябва да е auto, always или never")
    lang = check_lang(query.get("lang", lang))
    services = get_services(request.app)

    if file is not None and file.filename:
        data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Снимката е над {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        return analyze(services, open_image(data), file.filename, top, verify, lang)

    url = url or query.get("url")
    if url:
        url = unwrap_image_url(url, query)
        return analyze(services, open_image(download_image(url)), url, top, verify, lang)
    raise HTTPException(400, "Подай или 'file', или 'url'")


@app.get("/predict", response_model=PredictResponse, tags=["landmarks"], dependencies=[Depends(require_api_key)])
def predict_by_url(
    request: Request,
    url: str = Query(description="URL към снимка"),
    top: int = Query(3, ge=1, le=20, description="Колко кандидата да се върнат"),
    verify: VerifyMode = Query("auto", description=VERIFY_HELP),
    lang: str = Query(config.INFO_LANGUAGE, description=LANG_HELP),
):
    """Разпознава забележителност от URL (удобно за браузър)."""
    url = unwrap_image_url(url, request.query_params)
    img = open_image(download_image(url))
    return analyze(get_services(request.app), img, url, top, verify, check_lang(lang))

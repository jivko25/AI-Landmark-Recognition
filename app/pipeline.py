"""Recognition flow: local model -> (Gemini if unsure) -> Wikipedia info."""

from dataclasses import dataclass

from google.genai import errors
from pydantic import ValidationError

from app import config
from app.recognizer import LandmarkRecognizer
from app.schemas import Landmark, LandmarkInfo, PredictResponse, Verification
from app.verifier import GeminiVerifier, verification_reasons
from app.wiki import WikipediaClient

NO_LANDMARK = "На снимката не е разпозната забележителност"


@dataclass
class Services:
    recognizer: LandmarkRecognizer
    verifier: GeminiVerifier | None
    wiki: WikipediaClient


def resolve_landmark(services, img, candidates, verify):
    local = Landmark(name=candidates[0].name, score=candidates[0].score, source="local")
    reasons = verification_reasons(candidates)
    needed = verify == "always" or (verify == "auto" and bool(reasons))
    verification = Verification(needed=needed, reasons=reasons, status="skipped")

    if not needed:
        return local, verification, None
    if services.verifier is None:
        verification.status = "unavailable"
        verification.error = "Gemini не е настроен (няма GEMINI_API_KEY), върнат е локалният резултат"
        return local, verification, None

    try:
        result = services.verifier.verify(img, candidates)
    except errors.APIError as e:
        verification.status = "error"
        if e.code == 429:
            verification.error = "Безплатният лимит на Gemini е изчерпан за момента, върнат е локалният резултат"
        else:
            verification.error = f"Gemini върна грешка {e.code}, върнат е локалният резултат"
        return local, verification, None
    except ValidationError:
        verification.status = "error"
        verification.error = "Gemini върна неочакван отговор, върнат е локалният резултат"
        return local, verification, None
    except Exception as e:
        verification.status = "error"
        verification.error = f"Gemini не отговори ({type(e).__name__}), върнат е локалният резултат"
        return local, verification, None

    verification.gemini = result
    if not result.landmark:
        verification.status = "no_landmark"
        return Landmark(name=None, score=None, source="gemini"), verification, None
    if result.landmark.casefold() == local.name.casefold():
        verification.status = "confirmed"
        return local.model_copy(update={"source": "local+gemini"}), verification, result.wikipedia_title

    verification.status = "corrected"
    score = next((c.score for c in candidates if c.name.casefold() == result.landmark.casefold()), None)
    return Landmark(name=result.landmark, score=score, source="gemini"), verification, result.wikipedia_title


def analyze(services, img, source, top, verify, lang):
    candidates = services.recognizer.predict(img, max(top, config.GEMINI_CANDIDATES))
    landmark, verification, wikipedia_title = resolve_landmark(
        services, img, candidates[: config.GEMINI_CANDIDATES], verify
    )
    if landmark.name:
        info = services.wiki.lookup(landmark.name, wikipedia_title, lang)
    else:
        info = LandmarkInfo(found=False, message=NO_LANDMARK)
    return PredictResponse(
        source=source,
        landmark=landmark,
        info=info,
        candidates=candidates[:top],
        verification=verification,
    )

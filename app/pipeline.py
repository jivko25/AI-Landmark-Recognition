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
DISPUTED = "Не е сигурно коя е забележителността, затова не се връща информация"


@dataclass
class Services:
    recognizer: LandmarkRecognizer
    verifier: GeminiVerifier | None
    wiki: WikipediaClient


def describe_failure(failures):
    if any(isinstance(e, errors.APIError) and e.code == 429 for e in failures):
        return "Безплатният лимит на Gemini е изчерпан за момента, върнат е локалният резултат"
    codes = sorted({e.code for e in failures if isinstance(e, errors.APIError) and e.code})
    if codes and all(c >= 500 for c in codes):
        return f"Gemini е претоварен в момента (грешка {'/'.join(map(str, codes))}), върнат е локалният резултат"
    if any(isinstance(e, ValidationError) for e in failures):
        return "Gemini върна неочакван отговор, върнат е локалният резултат"
    if codes:
        return f"Gemini върна грешка {'/'.join(map(str, codes))}, върнат е локалният резултат"
    names = ", ".join(sorted({type(e).__name__ for e in failures})) or "без отговор"
    return f"Gemini не отговори ({names}), върнат е локалният резултат"


def same_landmark(a, b):
    if a.landmark is None or b.landmark is None:
        return a.landmark is None and b.landmark is None
    if a.landmark.casefold() == b.landmark.casefold():
        return True
    return bool(a.wikipedia_title and b.wikipedia_title and a.wikipedia_title.casefold() == b.wikipedia_title.casefold())


def resolve_landmark(services, img, candidates, verify):
    reasons = verification_reasons(candidates)
    needed = verify == "always" or (verify == "auto" and bool(reasons))
    local = Landmark(name=candidates[0].name, score=candidates[0].score, source="local", confident=not reasons)
    verification = Verification(needed=needed, reasons=reasons, status="skipped")

    if not needed:
        return local, verification, None
    if services.verifier is None:
        verification.status = "unavailable"
        verification.error = "Gemini не е настроен (няма GEMINI_API_KEY), върнат е локалният резултат"
        return local, verification, None

    answers, failures = services.verifier.verify(img, candidates)
    verification.answers = answers
    if not answers:
        verification.status = "error"
        verification.error = describe_failure(failures)
        return local, verification, None

    # Flash-Lite models sometimes name the wrong landmark with "high" confidence, so a guess or
    # two models that disagree is not treated as a confirmation.
    sure = [a for a in answers if a.confidence != "low"]
    if not sure or any(not same_landmark(sure[0], a) for a in sure[1:]):
        verification.status = "disputed"
        verification.error = (
            "Gemini моделите не са сигурни или не са съгласни помежду си, върнат е локалният резултат"
        )
        return local, verification, None

    result = sure[0]
    verification.gemini = result
    verification.agreement = "all" if len(sure) > 1 else "single"
    # Overriding the local model on the word of a single Gemini answer is not reliable enough.
    gemini_only_sure = verification.agreement == "all"
    if not result.landmark:
        verification.status = "no_landmark"
        return Landmark(name=None, score=None, source="gemini", confident=gemini_only_sure), verification, None
    if result.landmark.casefold() == local.name.casefold():
        verification.status = "confirmed"
        confirmed = local.model_copy(update={"source": "local+gemini", "confident": True})
        return confirmed, verification, result.wikipedia_title

    verification.status = "corrected"
    score = next((c.score for c in candidates if c.name.casefold() == result.landmark.casefold()), None)
    corrected = Landmark(name=result.landmark, score=score, source="gemini", confident=gemini_only_sure)
    return corrected, verification, result.wikipedia_title


def analyze(services, img, source, top, verify, lang):
    candidates = services.recognizer.predict(img, max(top, config.GEMINI_CANDIDATES))
    landmark, verification, wikipedia_title = resolve_landmark(
        services, img, candidates[: config.GEMINI_CANDIDATES], verify
    )
    if verification.status == "disputed":
        info = LandmarkInfo(found=False, message=DISPUTED)
    elif landmark.name:
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

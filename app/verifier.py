"""Second opinion from Gemini (free tier only) when the local model is unsure."""

import io

from google import genai
from google.genai import errors, types

from app import config
from app.schemas import GeminiResult, GeminiVerdict

PROMPT = """You are verifying the output of a landmark recognition model for European landmarks.
The model was unsure. Its top candidates (score 0-1, higher is more likely) are:
{candidates}

Look at the photo and decide which landmark it actually shows.
- If it is one of the candidates, return that candidate's exact name and set matches_candidate to true.
- If it is a different landmark you recognize (it may be outside Europe), return its common English name
  and set matches_candidate to false.
- If you cannot identify a specific landmark, return null for landmark and wikipedia_title.
Photos may be taken from unusual angles or show only part of a landmark. A building that is part of,
or directly behind, a more famous landmark (for example a palace behind a fountain) should be reported
as the more famous landmark."""


def verification_reasons(candidates):
    # Above VERIFY_SURE_SCORE nearby landmarks also score high (Eiffel Tower 0.99, Pont de Bir-Hakeim 0.97),
    # so a small margin there is normal and not a sign of confusion.
    top = candidates[0].score
    reasons = []
    if top < config.VERIFY_MIN_SCORE:
        reasons.append(f"най-високата оценка {top:.3f} е под {config.VERIFY_MIN_SCORE}")
    if len(candidates) > 1 and top < config.VERIFY_SURE_SCORE and top - candidates[1].score < config.VERIFY_MIN_MARGIN:
        reasons.append(f"първите два кандидата са твърде близо ({top:.3f} и {candidates[1].score:.3f})")
    return reasons


class GeminiVerifier:
    def __init__(self, api_key, models, timeout_s):
        if not models:
            raise ValueError("No free Gemini models configured")
        self.models = list(models)
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    def verify(self, img, candidates):
        """Ask the models in order; move to the next one on timeouts, rate limits or server errors.

        Free-tier latency varies a lot (the same request took 3 s and 60 s in testing), so each model
        gets its own timeout instead of one long wait.
        """
        small = img.copy()
        small.thumbnail((1024, 1024))
        buf = io.BytesIO()
        small.save(buf, format="JPEG", quality=90)

        contents = [
            PROMPT.format(candidates="\n".join(f"- {c.name} ({c.score:.2f})" for c in candidates)),
            types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
        ]
        cfg = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=GeminiVerdict,
        )

        last_error = None
        for model in self.models:
            try:
                response = self.client.models.generate_content(model=model, contents=contents, config=cfg)
            except errors.APIError as e:
                if e.code == 429 or (e.code or 0) >= 500:
                    last_error = e
                    continue
                raise
            except Exception as e:
                # Timeouts and connection errors come from google-genai's internal HTTP client (httpx2).
                last_error = e
                continue
            verdict = GeminiVerdict.model_validate_json(response.text)
            return GeminiResult(model=model, **verdict.model_dump())
        raise last_error

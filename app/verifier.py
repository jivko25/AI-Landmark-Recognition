"""Second opinion from Gemini (free tier only) when the local model is unsure."""

import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout

from google import genai
from google.genai import errors, types

from app import config
from app.schemas import GeminiResult, GeminiVerdict

PROMPT = """You are verifying the output of a landmark recognition model for European landmarks.
The model was unsure and is often wrong. Its top candidates (score 0-1, higher is more likely) are:
{candidates}

Look at the photo and decide which landmark it actually shows. The candidates may all be wrong:
do not pick one just because it is on the list, only if you clearly recognize it.
- If it is one of the candidates, return that candidate's exact name and set matches_candidate to true.
- If it is a different landmark you recognize (it may be outside Europe), return its common English name
  and set matches_candidate to false.
- If you cannot identify a specific landmark, return null for landmark and wikipedia_title.
- Use confidence "high" only if you are sure of this exact landmark; use "low" if you are guessing.
Photos may be taken from unusual angles or show only part of a landmark. A building that is part of,
or directly behind, a more famous landmark (for example a palace behind a fountain) should be reported
as the more famous landmark."""

OVERLOADED = {500, 502, 503, 504}


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
        self.timeout_s = timeout_s
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    def _ask(self, model, contents, cfg):
        # Free-tier models often answer 503/504 ("high demand") for a moment; one retry usually helps.
        for attempt in range(2):
            try:
                response = self.client.models.generate_content(model=model, contents=contents, config=cfg)
            except errors.APIError as e:
                if e.code in OVERLOADED and attempt == 0:
                    time.sleep(1)
                    continue
                raise
            verdict = GeminiVerdict.model_validate_json(response.text)
            return GeminiResult(model=model, **verdict.model_dump())

    def verify(self, img, candidates):
        """Ask all models at the same time and return (answers, errors).

        Asking in parallel keeps latency at the slowest model instead of the sum, and two answers
        let the caller catch a model that confidently names the wrong landmark.
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

        answers, failures = {}, []
        pool = ThreadPoolExecutor(max_workers=len(self.models))
        futures = {pool.submit(self._ask, m, contents, cfg): m for m in self.models}
        try:
            for future in as_completed(futures, timeout=self.timeout_s * 2 + 5):
                try:
                    answers[futures[future]] = future.result()
                except Exception as e:
                    failures.append(e)
        except FuturesTimeout:
            failures.append(TimeoutError("Gemini did not answer in time"))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return [answers[m] for m in self.models if m in answers], failures

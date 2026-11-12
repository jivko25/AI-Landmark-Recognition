from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.pipeline import Services
from app.recognizer import LandmarkRecognizer
from app.schemas import Candidate, GeminiResult, LandmarkInfo

DATA = Path(__file__).parent / "data"


class FakeRecognizer:
    landmarks_known = 3

    def __init__(self, candidates):
        self.candidates = candidates

    def predict(self, img, top):
        return self.candidates[:top]


class FakeVerifier:
    models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    def __init__(self, *answers, failures=()):
        self.answers = list(answers)
        self.failures = list(failures)
        self.calls = 0

    def verify(self, img, candidates):
        self.calls += 1
        return self.answers, self.failures


class FakeWiki:
    def __init__(self):
        self.calls = []

    def lookup(self, name, wikipedia_title=None, lang="bg"):
        self.calls.append((name, wikipedia_title, lang))
        return LandmarkInfo(found=True, title=name, summary=f"За {name}", language=lang, source="wikipedia")


UNSURE = [Candidate(name="Palazzo Poli", score=0.8466), Candidate(name="Trevi Fountain", score=0.8228)]
SURE = [Candidate(name="Eiffel Tower", score=0.9865), Candidate(name="Pont de Bir-Hakeim", score=0.96)]


def gemini(landmark, wikipedia_title=None, matches=True, confidence="high", model="gemini-3.5-flash-lite"):
    return GeminiResult(
        model=model,
        landmark=landmark,
        wikipedia_title=wikipedia_title,
        matches_candidate=matches,
        confidence=confidence,
        reason="тест",
    )


@pytest.fixture(scope="session")
def real_recognizer():
    return LandmarkRecognizer(config.MODEL_PATH)


@pytest.fixture
def make_client():
    def _make(recognizer, verifier=None, wiki=None):
        app.state.services = Services(recognizer=recognizer, verifier=verifier, wiki=wiki or FakeWiki())
        return TestClient(app)

    yield _make
    app.state.services = None


@pytest.fixture
def image_bytes():
    return (DATA / "eiffel.jpg").read_bytes()

import json

from google.genai import errors
from PIL import Image

from app.schemas import Candidate
from app.verifier import GeminiVerifier

CANDIDATES = [Candidate(name="Palazzo Poli", score=0.85), Candidate(name="Trevi Fountain", score=0.82)]
ANSWER = json.dumps(
    {"landmark": "Trevi Fountain", "wikipedia_title": "Trevi Fountain", "matches_candidate": True, "confidence": "high", "reason": "x"}
)


class Response:
    text = ANSWER


class FakeModels:
    def __init__(self, script):
        self.script = script  # model -> list of things to return/raise, in order
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        step = self.script[model].pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def make_verifier(script, monkeypatch):
    monkeypatch.setattr("app.verifier.time.sleep", lambda s: None)
    v = GeminiVerifier("key", list(script), timeout_s=5)
    v.client = type("Client", (), {"models": FakeModels(script)})()
    return v


def err(code):
    return errors.APIError(code, {"error": {"message": "x", "status": "x"}})


def img():
    return Image.new("RGB", (64, 64))


def test_asks_all_models(monkeypatch):
    v = make_verifier({"a": [Response()], "b": [Response()]}, monkeypatch)
    answers, failures = v.verify(img(), CANDIDATES)
    assert [a.model for a in answers] == ["a", "b"]
    assert failures == []


def test_retries_once_when_overloaded(monkeypatch):
    v = make_verifier({"a": [err(503), Response()]}, monkeypatch)
    answers, failures = v.verify(img(), CANDIDATES)
    assert len(answers) == 1 and failures == []
    assert v.client.models.calls == ["a", "a"]


def test_gives_up_after_second_overload(monkeypatch):
    v = make_verifier({"a": [err(504), err(504)], "b": [Response()]}, monkeypatch)
    answers, failures = v.verify(img(), CANDIDATES)
    assert [a.model for a in answers] == ["b"]
    assert [f.code for f in failures] == [504]


def test_no_retry_on_rate_limit(monkeypatch):
    v = make_verifier({"a": [err(429)]}, monkeypatch)
    answers, failures = v.verify(img(), CANDIDATES)
    assert answers == [] and failures[0].code == 429
    assert v.client.models.calls == ["a"]

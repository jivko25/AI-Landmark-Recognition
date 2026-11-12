from google.genai import errors

from app import config
from tests.conftest import SURE, UNSURE, FakeRecognizer, FakeVerifier, FakeWiki, gemini


def post_file(client, image_bytes, **data):
    return client.post("/predict", files={"file": ("photo.jpg", image_bytes, "image/jpeg")}, data=data)


def test_real_model_recognizes_eiffel_tower(make_client, real_recognizer, image_bytes):
    client = make_client(real_recognizer)
    body = post_file(client, image_bytes).json()
    assert body["landmark"]["name"] == "Eiffel Tower"
    assert body["verification"]["status"] == "skipped"
    assert body["info"]["found"] is True


def test_health(make_client):
    body = make_client(FakeRecognizer(SURE), FakeVerifier()).get("/health").json()
    assert body["status"] == "ok" and body["gemini_enabled"] is True


def api_error(code, status):
    return errors.APIError(code, {"error": {"message": status, "status": status}})


LITE = "gemini-3.1-flash-lite"


def test_sure_result_skips_gemini(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Something else"))
    body = post_file(make_client(FakeRecognizer(SURE), verifier), image_bytes).json()
    assert verifier.calls == 0
    assert body["landmark"] == {"name": "Eiffel Tower", "score": 0.9865, "source": "local", "confident": True}


def test_both_models_agree_and_correct(make_client, image_bytes):
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini("Trevi Fountain", "Trevi Fountain"), gemini("trevi fountain", model=LITE))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["landmark"] == {"name": "Trevi Fountain", "score": 0.8228, "source": "gemini", "confident": True}
    assert body["verification"]["status"] == "corrected"
    assert body["verification"]["agreement"] == "all"
    assert len(body["verification"]["answers"]) == 2
    assert wiki.calls == [("Trevi Fountain", "Trevi Fountain", "bg")]


def test_models_agree_by_wikipedia_title(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Fontana di Trevi", "Trevi Fountain"), gemini("Trevi Fountain", "Trevi Fountain", model=LITE))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier), image_bytes).json()
    assert body["verification"]["status"] == "corrected"


def test_models_disagree_is_disputed(make_client, image_bytes):
    # Real case: Defenders of Stara Zagora memorial; one model said The Brooding Soldier, the other Pantheon in Ruse.
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini("Palazzo Poli"), gemini("Pantheon of National Revival Heroes", model=LITE))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["verification"]["status"] == "disputed"
    assert body["landmark"] == {"name": "Palazzo Poli", "score": 0.8466, "source": "local", "confident": False}
    assert body["verification"]["gemini"] is None
    assert body["info"]["found"] is False and wiki.calls == []


def test_low_confidence_is_not_a_confirmation(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Palazzo Poli", confidence="low"))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier), image_bytes).json()
    assert body["verification"]["status"] == "disputed"
    assert body["landmark"]["confident"] is False


def test_low_confidence_answer_is_ignored_when_other_is_sure(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Trevi Fountain"), gemini("Something", confidence="low", model=LITE))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier), image_bytes).json()
    assert body["verification"]["status"] == "corrected"
    assert body["verification"]["agreement"] == "single"
    assert body["landmark"]["confident"] is False


def test_one_model_overloaded_other_confirms(make_client, image_bytes):
    verifier = FakeVerifier(gemini("palazzo poli"), failures=[api_error(504, "DEADLINE_EXCEEDED")])
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier), image_bytes).json()
    assert body["landmark"]["source"] == "local+gemini"
    assert body["landmark"]["confident"] is True
    assert body["verification"]["status"] == "confirmed"
    assert body["verification"]["agreement"] == "single"


def test_single_correction_is_not_confident(make_client, image_bytes):
    # Real case: the other model was overloaded and this one wrongly named the Pantheon in Ruse.
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini("Pantheon of National Revival Heroes"), failures=[api_error(503, "UNAVAILABLE")])
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["verification"]["status"] == "corrected"
    assert body["landmark"] == {
        "name": "Pantheon of National Revival Heroes", "score": None, "source": "gemini", "confident": False,
    }
    assert wiki.calls


def test_gemini_sees_no_landmark(make_client, image_bytes):
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini(None, matches=False), gemini(None, matches=False, model=LITE))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["landmark"]["name"] is None
    assert body["verification"]["status"] == "no_landmark"
    assert body["info"]["found"] is False
    assert wiki.calls == []


def test_all_models_overloaded(make_client, image_bytes):
    failures = [api_error(504, "DEADLINE_EXCEEDED"), api_error(503, "UNAVAILABLE")]
    body = post_file(make_client(FakeRecognizer(UNSURE), FakeVerifier(failures=failures)), image_bytes).json()
    assert body["verification"]["status"] == "error"
    assert "претоварен" in body["verification"]["error"] and "503/504" in body["verification"]["error"]
    assert body["landmark"]["confident"] is False


def test_gemini_rate_limit_falls_back_to_local(make_client, image_bytes):
    failures = [api_error(429, "RESOURCE_EXHAUSTED"), api_error(503, "UNAVAILABLE")]
    body = post_file(make_client(FakeRecognizer(UNSURE), FakeVerifier(failures=failures)), image_bytes).json()
    assert body["landmark"]["source"] == "local"
    assert "лимит" in body["verification"]["error"]


def test_gemini_timeout_falls_back_to_local(make_client, image_bytes):
    body = post_file(make_client(FakeRecognizer(UNSURE), FakeVerifier(failures=[TimeoutError()])), image_bytes).json()
    assert body["landmark"]["name"] == "Palazzo Poli"
    assert body["verification"]["status"] == "error"
    assert "TimeoutError" in body["verification"]["error"]


def test_no_gemini_configured(make_client, image_bytes):
    body = post_file(make_client(FakeRecognizer(UNSURE)), image_bytes).json()
    assert body["verification"]["status"] == "unavailable"
    assert body["landmark"]["confident"] is False


def test_verify_never_and_always(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Eiffel Tower"))
    client = make_client(FakeRecognizer(SURE), verifier)
    assert post_file(client, image_bytes, verify="never").json()["verification"]["status"] == "skipped"
    assert post_file(client, image_bytes, verify="always").json()["verification"]["status"] == "confirmed"
    assert verifier.calls == 1


def test_lang_is_passed_to_wiki(make_client, image_bytes):
    wiki = FakeWiki()
    post_file(make_client(FakeRecognizer(SURE), wiki=wiki), image_bytes, lang="de")
    assert wiki.calls[0][2] == "de"


def test_bad_params(make_client, image_bytes):
    client = make_client(FakeRecognizer(SURE))
    assert client.post("/predict").status_code == 400
    assert post_file(client, image_bytes, verify="maybe").status_code in (400, 422)
    assert post_file(client, image_bytes, lang="bulgarian").status_code == 400
    assert post_file(client, b"not an image").status_code == 400


def test_upload_too_large(make_client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    client = make_client(FakeRecognizer(SURE))
    assert post_file(client, b"x" * 11).status_code == 413


def test_url_to_internal_address_is_blocked(make_client):
    client = make_client(FakeRecognizer(SURE))
    assert client.get("/predict", params={"url": "http://127.0.0.1:8000/health"}).status_code == 400
    assert client.post("/predict?url=http://localhost/x.jpg").status_code == 400


def test_url_flow(make_client, image_bytes, monkeypatch):
    monkeypatch.setattr("app.main.download_image", lambda url: image_bytes)
    client = make_client(FakeRecognizer(SURE))
    assert client.get("/predict", params={"url": "https://example.com/a.jpg"}).json()["source"] == "https://example.com/a.jpg"
    assert client.post("/predict", data={"url": "https://example.com/b.jpg"}).json()["source"] == "https://example.com/b.jpg"
    assert client.post("/predict?url=https://example.com/c.jpg").json()["source"] == "https://example.com/c.jpg"


def test_api_keys(make_client, image_bytes, monkeypatch):
    monkeypatch.setattr(config, "API_KEYS", frozenset({"secret"}))
    client = make_client(FakeRecognizer(SURE))
    assert post_file(client, image_bytes).status_code == 401
    ok = client.post("/predict", files={"file": ("p.jpg", image_bytes)}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200

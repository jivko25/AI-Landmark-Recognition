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


def test_sure_result_skips_gemini(make_client, image_bytes):
    verifier = FakeVerifier(gemini("Something else"))
    body = post_file(make_client(FakeRecognizer(SURE), verifier), image_bytes).json()
    assert verifier.calls == 0
    assert body["landmark"] == {"name": "Eiffel Tower", "score": 0.9865, "source": "local"}


def test_gemini_corrects_unsure_result_and_info_uses_its_title(make_client, image_bytes):
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini("Trevi Fountain", "Trevi Fountain"))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["landmark"] == {"name": "Trevi Fountain", "score": 0.8228, "source": "gemini"}
    assert body["verification"]["status"] == "corrected"
    assert wiki.calls == [("Trevi Fountain", "Trevi Fountain", "bg")]


def test_gemini_confirms(make_client, image_bytes):
    verifier = FakeVerifier(gemini("palazzo poli"))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier), image_bytes).json()
    assert body["landmark"]["source"] == "local+gemini"
    assert body["verification"]["status"] == "confirmed"


def test_gemini_sees_no_landmark(make_client, image_bytes):
    wiki = FakeWiki()
    verifier = FakeVerifier(gemini(None, matches=False))
    body = post_file(make_client(FakeRecognizer(UNSURE), verifier, wiki), image_bytes).json()
    assert body["landmark"]["name"] is None
    assert body["info"]["found"] is False
    assert wiki.calls == []


def test_gemini_rate_limit_falls_back_to_local(make_client, image_bytes):
    error = errors.APIError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    body = post_file(make_client(FakeRecognizer(UNSURE), FakeVerifier(error=error)), image_bytes).json()
    assert body["landmark"]["source"] == "local"
    assert body["verification"]["status"] == "error"
    assert "лимит" in body["verification"]["error"]


def test_gemini_crash_falls_back_to_local(make_client, image_bytes):
    body = post_file(make_client(FakeRecognizer(UNSURE), FakeVerifier(error=TimeoutError())), image_bytes).json()
    assert body["landmark"]["name"] == "Palazzo Poli"
    assert body["verification"]["status"] == "error"


def test_no_gemini_configured(make_client, image_bytes):
    body = post_file(make_client(FakeRecognizer(UNSURE)), image_bytes).json()
    assert body["verification"]["status"] == "unavailable"


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

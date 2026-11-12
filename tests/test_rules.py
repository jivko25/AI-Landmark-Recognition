from app import config
from app.schemas import Candidate
from app.verifier import verification_reasons
from app.wiki import pick_search_result, word_overlap


def c(*scores):
    return [Candidate(name=f"L{i}", score=s) for i, s in enumerate(scores)]


def test_confident_result_needs_no_verification():
    assert verification_reasons(c(0.89, 0.74)) == []


def test_low_score_needs_verification():
    reasons = verification_reasons(c(0.75, 0.60))
    assert len(reasons) == 1 and "под" in reasons[0]


def test_close_candidates_need_verification():
    reasons = verification_reasons(c(0.90, 0.88))
    assert len(reasons) == 1 and "близо" in reasons[0]


def test_close_candidates_ignored_when_very_sure():
    # Eiffel Tower 0.99 vs. the bridge next to it 0.97 is normal, not confusion.
    assert verification_reasons(c(0.9865, 0.96)) == []


def test_trevi_example_triggers_both_rules():
    assert len(verification_reasons(c(0.8466, 0.8228))) == 2


def test_free_models_only():
    assert all(m in config.FREE_GEMINI_MODELS for m in config.GEMINI_MODELS)
    assert "gemini-4-argon" not in config.FREE_GEMINI_MODELS


def test_word_overlap_handles_spelling_variants():
    assert word_overlap("Marcello Theater", "Theatre of Marcellus") == 1.0
    assert word_overlap("Ste-Marie-Madeleine", "Rive-de-Gier") == 0.0


def page(title, index, coords=True, disambiguation=False):
    p = {"title": title, "index": index}
    if coords:
        p["coordinates"] = [{"lat": 1, "lon": 2}]
    if disambiguation:
        p["pageprops"] = {"disambiguation": ""}
    return p


def test_pick_skips_people_and_takes_matching_place():
    pages = [page("Marcello Hernández", 1, coords=False), page("Theatre of Marcellus", 2)]
    assert pick_search_result("Marcello Theater", pages) == "Theatre of Marcellus"


def test_pick_accepts_top_place_even_with_different_wording():
    pages = [page("Saint Alexander Nevsky Cathedral, Sofia", 1), page("National symbols of Bulgaria", 2, coords=False)]
    assert pick_search_result("Cathedral Saint Aleksandar Nevski", pages) == "Saint Alexander Nevsky Cathedral, Sofia"


def test_pick_rejects_unrelated_places():
    pages = [page("Bonaventure", 1, coords=False), page("Rive-de-Gier", 2), page("Sainte-Marie-aux-Mines", 3)]
    assert pick_search_result("Ste-Marie-Madeleine", pages) is None


def test_pick_skips_disambiguation_pages():
    assert pick_search_result("Coliseum", [page("Coliseum", 1, disambiguation=True)]) is None

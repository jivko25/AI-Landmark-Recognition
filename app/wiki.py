"""Landmark information from Wikipedia (free, no API key)."""

import re
import unicodedata

import requests

from app import config
from app.schemas import Coordinates, LandmarkInfo

NO_INFO = "Няма информация за тази забележителност"
SEARCH_RESULTS = 5
CACHE_SIZE = 512


def _tokens(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z0-9]+", text) if len(t) >= 4]


def word_overlap(name, title):
    """Share of the name's words that also appear in the title, compared by their first 5 letters
    so that spelling variants match (Marcello Theater ~ Theatre of Marcellus)."""
    name_tokens = _tokens(name)
    if not name_tokens:
        return 0.0
    title_stems = {t[:5] for t in _tokens(title)}
    return sum(t[:5] in title_stems for t in name_tokens) / len(name_tokens)


def pick_search_result(name, pages):
    """Search is fuzzy ("Marcello Theater" finds a comedian first), so accept only a place
    (has coordinates, not a disambiguation page) that is either the top hit or clearly matches the name."""
    for i, page in enumerate(sorted(pages, key=lambda p: p.get("index", 0))):
        if "disambiguation" in page.get("pageprops", {}) or not page.get("coordinates"):
            continue
        if i == 0 or word_overlap(name, page["title"]) > 0.5:
            return page["title"]
    return None


class WikipediaClient:
    def __init__(self, user_agent=config.USER_AGENT, timeout_s=config.WIKIPEDIA_TIMEOUT_S):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.timeout_s = timeout_s
        self._cache = {}

    def lookup(self, name, wikipedia_title=None, lang="bg"):
        key = (name, wikipedia_title, lang)
        if key not in self._cache:
            info = self._lookup(name, wikipedia_title, lang)
            if info.source is None and info.message != NO_INFO:
                return info  # a network error, try again next time
            if len(self._cache) >= CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = info
        return self._cache[key].model_copy(deep=True)

    def _api(self, lang, **params):
        resp = self.session.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "format": "json", "formatversion": 2, "redirects": 1, **params},
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        return resp.json().get("query", {})

    def _search(self, name):
        query = self._api(
            "en",
            generator="search",
            gsrsearch=name,
            gsrlimit=SEARCH_RESULTS,
            prop="coordinates|pageprops",
            ppprop="disambiguation",
        )
        return pick_search_result(name, query.get("pages", []))

    def _page(self, lang, title, langlink=None):
        params = {
            "titles": title,
            "prop": "extracts|coordinates|pageimages|info|pageprops",
            "exintro": 1,
            "explaintext": 1,
            "exsentences": 4,
            "inprop": "url",
            "piprop": "thumbnail",
            "pithumbsize": 640,
            "ppprop": "disambiguation",
        }
        if langlink:
            params["prop"] += "|langlinks"
            params["lllang"] = langlink
        pages = self._api(lang, **params).get("pages", [])
        page = pages[0] if pages else None
        if not page or page.get("missing") or "disambiguation" in page.get("pageprops", {}):
            return None
        return page

    def _lookup(self, name, wikipedia_title=None, lang="bg"):
        try:
            langlink = lang if lang != "en" else None
            page = self._page("en", wikipedia_title, langlink) if wikipedia_title else None
            if page is None:
                title = self._search(name)
                page = self._page("en", title, langlink) if title else None
            if page is None:
                return LandmarkInfo(found=False, message=NO_INFO)

            coords = page.get("coordinates") or []
            info = LandmarkInfo(
                found=True,
                title=page["title"],
                summary=page.get("extract") or None,
                language="en",
                url=page.get("fullurl"),
                image=(page.get("thumbnail") or {}).get("source"),
                coordinates=Coordinates(lat=coords[0]["lat"], lon=coords[0]["lon"]) if coords else None,
                english_title=page["title"],
                english_url=page.get("fullurl"),
                source="wikipedia",
            )

            local_title = next((ll["title"] for ll in page.get("langlinks", []) if ll.get("lang") == lang), None)
            if local_title:
                local = self._page(lang, local_title)
                if local and local.get("extract"):
                    info.title = local["title"]
                    info.summary = local["extract"]
                    info.language = lang
                    info.url = local.get("fullurl")
            return info
        except (requests.RequestException, ValueError, KeyError) as e:
            return LandmarkInfo(found=False, message=f"{NO_INFO} (Wikipedia не отговори: {type(e).__name__})")

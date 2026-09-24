"""Tests for the photo finder (app/live/photos.py). No network: every Wikipedia/Commons/Wikidata call is faked."""
import pytest

from app.live import photos

LICENSED = {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a>Jane Doe</a>"},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}
NON_COMMERCIAL = {"LicenseShortName": {"value": "CC BY-NC 2.0"}, "Artist": {"value": "Someone"}}


def imageinfo(titles: str, meta_for=lambda name: LICENSED) -> dict:
    pages = []
    for t in titles.split("|"):
        name = t.removeprefix("File:")
        pages.append({"title": t, "imageinfo": [{
            "thumburl": f"https://upload.example/{name}", "descriptionurl": f"https://commons.example/{t}",
            "extmetadata": meta_for(name),
        }]})
    return {"query": {"pages": pages}}


@pytest.fixture
def online(monkeypatch):
    """Pretend to be online, with an in-memory cache that behaves like app.live.http.cached."""
    store = {}

    def fake_cached(key, ttl, fetch):
        if key not in store:
            store[key] = fetch()
        return store[key]

    monkeypatch.setattr(photos, "offline", lambda: False)
    monkeypatch.setattr(photos, "cached", fake_cached)
    return store


def test_offline_never_looks_anything_up(monkeypatch):
    monkeypatch.setattr(photos, "get_json", lambda *a, **k: pytest.fail("network used offline"))
    assert photos.find_photo({"name": "Float in the Dead Sea"}, "Tel Aviv") is None
    items = [{"name": "Safari"}]
    photos.fill(items, "Tel Aviv")
    assert "photo_url" not in items[0]


def test_osm_wikipedia_link_gives_the_exact_photo_with_credit(online, monkeypatch):
    def fake(url, params, **kw):
        if "he.wikipedia" in url or "en.wikipedia" in url and params.get("titles") == "Ramat Gan Safari":
            return {"query": {"pages": [{"pageimage": "Safari_park.jpg"}]}}
        if params.get("prop") == "imageinfo":
            return imageinfo(params["titles"])
        pytest.fail(f"unexpected call {url} {params}")

    monkeypatch.setattr(photos, "get_json", fake)
    hit = photos.find_photo({"name": "ספארי", "type": "attraction", "wikipedia": "en:Ramat Gan Safari"}, "Tel Aviv")
    assert hit["url"].endswith("Safari park.jpg")
    assert hit["credit"] == {"author": "Jane Doe", "license": "CC BY-SA 4.0",
                             "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
                             "source": "https://commons.example/File:Safari park.jpg"}


def test_search_hit_about_something_else_is_rejected(online, monkeypatch):
    """A Wikipedia search for an activity often returns unrelated articles; they must not become its photo."""
    def fake(url, params, **kw):
        if params.get("generator") == "search":
            return {"query": {"pages": [{"index": 1, "title": "Linear park", "pageimage": "Highline.jpg"}]}}
        if params.get("list") == "search":
            return {"query": {"search": []}}
        if params.get("prop") == "imageinfo":
            pytest.fail("an unrelated photo was considered")
        pytest.fail(f"unexpected call {params}")

    monkeypatch.setattr(photos, "get_json", fake)
    assert photos.find_photo({"name": "Sunset promenade walk"}, "Tel Aviv") is None


def test_commons_search_retries_with_the_proper_name(online, monkeypatch):
    """Commons needs every word to match, so "Sunset sail Tagus" finds nothing but "Tagus sunset" does."""
    searched = []

    def fake(url, params, **kw):
        if params.get("generator") == "search":
            return {"query": {"pages": []}}
        if params.get("list") == "search":
            searched.append(params["srsearch"])
            hits = [] if params["srsearch"].startswith("Sunset sail Tagus") else [{"title": "File:Sunset Sailing on Tagus River.jpg"}]
            return {"query": {"search": hits}}
        if params.get("prop") == "imageinfo":
            return imageinfo(params["titles"])
        pytest.fail(f"unexpected call {params}")

    monkeypatch.setattr(photos, "get_json", fake)
    hit = photos.find_photo({"name": "Sunset sail on the Tagus"}, "Lisbon")
    assert hit["url"].endswith("Sunset Sailing on Tagus River.jpg")
    assert searched[0].startswith("Sunset sail Tagus") and "Tagus" in searched[1]


def test_generic_activity_must_match_the_city(online, monkeypatch):
    def fake(url, params, **kw):
        if params.get("generator") == "search":
            return {"query": {"pages": []}}
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "File:Desert safari in Namibia.jpg"}, {"title": "File:Dubai Desert Safari.jpg"}]}}
        if params.get("prop") == "imageinfo":
            return imageinfo(params["titles"])
        pytest.fail(f"unexpected call {params}")

    monkeypatch.setattr(photos, "get_json", fake)
    assert photos.find_photo({"name": "Desert safari"}, "Dubai")["url"].endswith("Dubai Desert Safari.jpg")


def test_beach_uses_photos_taken_there_but_not_event_photos_or_bad_licences(online, monkeypatch):
    def fake(url, params, **kw):
        if params.get("list") == "geosearch":
            return {"query": {"geosearch": [
                {"title": "File:Protest at Hilton beach.jpg"},
                {"title": "File:Hotel lobby.jpg"},
                {"title": "File:Beach at dusk NC.jpg"},
                {"title": "File:Evening at The Beach.jpg"},
            ]}}
        if params.get("prop") == "imageinfo":
            assert "Protest" not in params["titles"] and "lobby" not in params["titles"]
            return imageinfo(params["titles"], lambda n: NON_COMMERCIAL if "NC" in n else LICENSED)
        pytest.fail(f"unexpected call {params}")

    monkeypatch.setattr(photos, "get_json", fake)
    hit = photos.find_photo({"name": "חוף", "type": "beach", "lat": 32.08, "lng": 34.77}, "Tel Aviv")
    assert hit["url"].endswith("Evening at The Beach.jpg")


def test_a_failed_lookup_is_not_cached_as_no_photo(online, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("Wikimedia is down")

    monkeypatch.setattr(photos, "get_json", down)
    assert photos.find_photo({"name": "Float in the Dead Sea", "photo_query": "Dead Sea"}, "Tel Aviv") is None
    assert online == {}  # nothing stored, so the next search tries again


def test_fill_adds_photos_only_where_missing(online, monkeypatch):
    monkeypatch.setattr(photos, "find_photo", lambda item, city: {"url": "https://x/p.jpg", "credit": {"license": "CC0"}})
    items = [{"name": "Has bundled", "photo": "NAP-pizza"}, {"name": "Has live", "photo_url": "https://keep.jpg"}, {"name": "Bare"}]
    photos.fill(items, "Naples")
    assert "photo_url" not in items[0]
    assert items[1]["photo_url"] == "https://keep.jpg"
    assert items[2]["photo_url"] == "https://x/p.jpg" and items[2]["photo_credit"] == {"license": "CC0"}

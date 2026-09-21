"""Tonight: clubs and bars for one evening. Pure logic and fixtures, no network."""
from datetime import date, timedelta

import pytest

from app.live import catalog, nightlife
from tests.test_partners import approve, deal_body, fresh_limits, signup, submit  # noqa: F401  (fixture is reused)

FRI, MON, SUN = date(2026, 9, 25), date(2026, 9, 21), date(2026, 9, 27)
OPO = catalog.BY_CODE["OPO"]


def test_test_dates_are_the_weekdays_the_tests_assume():
    assert (FRI.weekday(), MON.weekday(), SUN.weekday()) == (4, 0, 6)


@pytest.mark.parametrize("hours,day,expected_open,expected_hours", [
    ("Fr,Sa 23:00-06:00", FRI, True, "23:00–06:00"),
    ("Fr,Sa 23:00-06:00", MON, False, None),
    ("Mo-Su 22:00-04:00", MON, True, "22:00–04:00"),
    ("Mo-Fr 09:00-17:00", FRI, False, None),
    ("Tu-Sa 18:00-02:00", FRI, True, "18:00–02:00"),
    ("24/7", SUN, True, "00:00–00:00"),
    ("Mo-Su 10:00-23:00; Su off", SUN, False, None),
    ("Mo-Su 20:00-02:00; PH off", MON, True, "20:00–02:00"),
    ("Mo-Th,Su 17:00-01:00", FRI, False, None),
    ("Sa-Mo 22:00-05:00", MON, True, "22:00–05:00"),
    ("Mo-Su 12:00-15:00,22:00-03:00", MON, True, "22:00–03:00"),
])
def test_opening_hours_for_tonight(hours, day, expected_open, expected_hours):
    result = nightlife.tonight(hours, day)
    assert result["open"] is expected_open
    if expected_hours and hours != "24/7":
        assert result["hours"] == expected_hours


@pytest.mark.parametrize("hours", [None, "", "   ", "sunrise-sunset", "Mo-Fr by appointment", "Mo-Su 25 hours"])
def test_hours_that_are_missing_or_unreadable_are_unknown_not_closed(hours):
    assert nightlife.tonight(hours, FRI) == {"open": None, "hours": None}


def test_late_night_venues_outrank_early_closers():
    early = venue("a", "Early Bar", kind="pub", hours="Mo-Su 12:00-23:00")
    late = venue("b", "Late Bar", kind="pub", hours="Mo-Su 12:00-03:00")
    ranked, _ = nightlife.rank_venues([early, late], FRI)
    assert [v["name"] for v in ranked] == ["Late Bar", "Early Bar"] and "Open past midnight" in ranked[0]["why"]
    assert "Open past midnight" not in ranked[1]["why"]


def test_photo_must_carry_the_venues_own_name():
    assert nightlife.matches_name("Maus Hábitos Porto exterior.jpg", "Maus Hábitos")
    assert not nightlife.matches_name("Ribeira Porto panorama.jpg", "Maus Hábitos")
    assert not nightlife.matches_name("Anything.jpg", "The Bar")  # only generic words: never guess
    assert nightlife.matches_name("Passeio Alegre club sunset.jpg", "Club Passeio Alegre")
    assert not nightlife.matches_name("Passeio dos Clérigos.jpg", "Club Passeio Alegre")


def page(title, license_="CC BY-SA 4.0", thumb="https://upload.example/t.jpg", index=1):
    return {"title": f"File:{title}", "index": index, "imageinfo": [{
        "thumburl": thumb, "descriptionurl": f"https://commons.example/{title}",
        "extmetadata": {"LicenseShortName": {"value": license_}, "Artist": {"value": "<a>Ana Silva</a>"}, "LicenseUrl": {"value": "https://cc"}}}]}


def test_pick_photo_keeps_only_matching_reusable_photos_with_credit():
    pages = [
        page("Some map of Porto.svg"),
        page("Passeio Alegre nightclub.jpg", license_="CC BY-NC 4.0", index=2),
        page("Passeio Alegre nightclub interior.jpg", index=3),
    ]
    got = nightlife.pick_photo(pages, "Passeio Alegre")
    assert got["url"] == "https://upload.example/t.jpg"
    assert got["credit"] == {"author": "Ana Silva", "license": "CC BY-SA 4.0", "license_url": "https://cc", "source": "https://commons.example/Passeio Alegre nightclub interior.jpg"}
    assert nightlife.pick_photo([page("Unrelated street.jpg")], "Passeio Alegre") is None


def venue(id_, name, kind="nightclub", hours="Fr,Sa 23:00-06:00", notable=False, website=None, dist=1.0, lat=41.14, lng=-8.61):
    return {"id": id_, "type": kind, "name": name, "lat": lat, "lng": lng, "distance_to_center_km": dist,
            "website": website, "opening_hours": hours, "notable": notable, "wikipedia": None, "osm_url": "u"}


def test_closed_venues_are_hidden_and_counted_and_notable_open_ones_lead():
    places = [
        venue("a", "Quiet Closed", hours="Mo-Th 20:00-23:00"),
        venue("b", "Famous Club", notable=True, website="https://x"),
        venue("c", "Plain Club"),
        venue("d", "Unknown Hours Bar", kind="pub", hours=None, notable=True),
    ]
    ranked, closed = nightlife.rank_venues(places, FRI)
    assert closed == 1
    assert [v["name"] for v in ranked] == ["Famous Club", "Plain Club", "Unknown Hours Bar"]
    assert ranked[0]["why"][:2] == ["Open tonight 23:00–06:00", "Open past midnight"]
    unknown = next(v for v in ranked if v["name"] == "Unknown Hours Bar")
    assert unknown["tonight"]["open"] is None and "Check before you go" in unknown["why"][0]
    assert unknown["kind_label"] == "Bar or pub"


def deal(id_, lat, lng, price=15.0):
    return {"id": id_, "title": "Entry with a drink", "lat": lat, "lng": lng, "price": price, "category": "party",
            "currency": "EUR", "partner": True, "discount_pct": 0, "tags": [], "days_left": 5}


def test_a_price_appears_only_when_a_real_deal_exists_and_never_invented():
    places = [venue("a", "Deal Club", lat=41.1400, lng=-8.6100), venue("b", "No Deal Club", lat=41.2000, lng=-8.7000)]
    out = nightlife.build(OPO, FRI, places, [deal(7, 41.1401, -8.6100), deal(8, 41.5, -8.9)], [])
    by = {v["name"]: v for v in out["venues"]}
    assert by["Deal Club"]["price"] == 15.0 and by["Deal Club"]["deal"]["id"] == 7 and by["Deal Club"]["price_note"] is None
    assert by["No Deal Club"]["price"] is None and by["No Deal Club"]["price_note"] == nightlife.NO_PRICE
    assert [d["id"] for d in out["deals"]] == [8]  # the deal not attached to a venue is listed separately
    assert "reviews" in out["ranking_note"] and "ticket prices" in out["ranking_note"]


def test_a_deal_belongs_to_only_the_nearest_venue():
    places = [venue("a", "Far Club", lat=41.14020, lng=-8.6100), venue("b", "Near Club", lat=41.14002, lng=-8.6100)]
    out = nightlife.build(OPO, FRI, places, [deal(7, 41.14000, -8.6100)], [])
    by = {v["name"]: v for v in out["venues"]}
    assert by["Near Club"]["deal"]["id"] == 7 and by["Far Club"]["deal"] is None and by["Far Club"]["price"] is None
    assert out["deals"] == []


def test_photos_are_attached_and_a_failing_photo_lookup_does_not_break_the_page():
    def photo_fn(name, city):
        if name == "Boom":
            raise RuntimeError("Commons is down")
        return {"url": "https://img/x.jpg", "credit": {"author": "A", "license": "CC0", "source": "s"}} if name == "Lit Club" else None

    out = nightlife.build(OPO, FRI, [venue("a", "Lit Club"), venue("b", "Boom"), venue("c", "Bare Club")], [], [], photo_fn=photo_fn)
    by = {v["name"]: v for v in out["venues"]}
    assert by["Lit Club"]["photo_url"] == "https://img/x.jpg" and by["Lit Club"]["photo_credit"]["license"] == "CC0"
    assert by["Boom"]["photo_url"] is None and by["Bare Club"]["photo_url"] is None
    assert out["venues"][0]["name"] == "Lit Club"  # a real photo is a small ranking bonus


def test_events_are_limited_to_the_chosen_day_and_sorted_by_time():
    events = [
        {"id": "1", "title": "Late", "date": FRI.isoformat(), "time": "23:00"},
        {"id": "2", "title": "Other day", "date": SUN.isoformat(), "time": "20:00"},
        {"id": "3", "title": "Early", "date": FRI.isoformat(), "time": "19:00"},
        {"id": "4", "title": "No time", "date": FRI.isoformat(), "time": None},
    ]
    assert [e["title"] for e in nightlife.build(OPO, FRI, [], [], events)["events"]] == ["Early", "Late", "No time"]


def test_valid_day_window():
    today = date.today()
    assert nightlife.valid_day(None) == today
    assert nightlife.valid_day(today + timedelta(days=14)) == today + timedelta(days=14)
    for bad in (today - timedelta(days=1), today + timedelta(days=15)):
        with pytest.raises(ValueError):
            nightlife.valid_day(bad)


# ---------------------------------------------------------------- endpoint (offline mode: partner deals only)

def test_tonight_endpoint_validates_and_shows_partner_deals_offline(client):
    assert client.get("/api/tonight", params={"dest": "Atlantis"}).status_code == 404
    assert client.get("/api/tonight", params={"dest": "OPO", "date": "2001-01-01"}).status_code == 422
    headers, _ = signup(client, name="Club Tonight")
    did = submit(client, headers, title="Entry and a drink before midnight", category="party", tags=["nightlife"], price=12.0, reference_price=20.0)
    approve(client, did)
    body = client.get("/api/tonight", params={"dest": "OPO"}).json()
    assert body["city"] == "Porto" and body["venues"] == [] and "ranking_note" in body
    assert did in [d["id"] for d in body["deals"]] and body["deals"][0]["partner"] is True
    assert any("Offline" in n for n in body["notes"])

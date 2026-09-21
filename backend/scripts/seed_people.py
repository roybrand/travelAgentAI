"""Fill Wayfinder People with clearly-labelled DEMO travelers, so the feature can be shown before real people join.

    python scripts/seed_people.py            # add demo travelers in Porto and Lisbon, each with an open request
    python scripts/seed_people.py --remove   # delete every demo traveler (and their plans, requests and chats)

Demo people are marked "demo" on their profile card, use @wayfinder.invalid emails, and have initials instead of photos
(no real person's photo is ever used). They are not real people and will not answer messages.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.partners import db  # noqa: E402
from app.social import intents, places, users  # noqa: E402

CITY = {"OPO": (41.1579, -8.6291), "LIS": (38.7223, -9.1393)}
TODAY = date.today()

DEMOS = [
    ("Rae", "OPO", "Here for two weeks. Love fado nights and long walks.", ["live-music", "coffee", "food"], ["English", "Portuguese"],
     "Live music tonight, someone relaxed", ("osm-node-demo-1", "Sala Fado (demo)", 41.1400, -8.6120)),
    ("Marco", "OPO", "Software developer on a work trip. Always up for good food.", ["food", "wine", "sightseeing"], ["English", "Italian"],
     "Dinner and wine tonight, somewhere local", ("osm-node-demo-2", "Tasca do Rio (demo)", 41.1405, -8.6136)),
    ("Lena", "OPO", "Photographer. I explore the old town at sunrise.", ["photography", "coffee", "art"], ["English", "German"],
     "Photo walk tomorrow morning, then coffee", None),
    ("Tomas", "LIS", "Local guide. Happy to show visitors around.", ["nightlife", "live-music", "sightseeing"], ["English", "Portuguese", "Spanish"],
     "Bars and live music tonight", ("osm-node-demo-3", "Bar Luz (demo)", 38.7108, -9.1366)),
    ("Yuki", "LIS", "Solo traveler from Osaka. Museums and ramen.", ["museums", "food", "art"], ["English", "Japanese"],
     "Museum this afternoon and then dinner", None),
]


def seed() -> None:
    for name, city, bio, interests, langs, ask, plan in DEMOS:
        email = f"demo-{name.lower()}@wayfinder.invalid"
        try:
            uid = users.register(email, "demo-password-not-secret", name, 1993, True, demo=True)["id"]
        except users.UserError:
            print(f"already there: {name}")
            continue
        users.update(uid, bio=bio, interests=interests, languages=langs, home_city=None)
        lat, lng = CITY[city]
        parsed = intents.parse(ask, TODAY)
        parsed["day"] = TODAY if "tomorrow" not in ask else parsed["day"]
        if parsed["tags"]:
            intents.create(uid, ask, lat, lng, 5000, parsed)
        if plan:
            key, place, plat, plng = plan
            places.attend(uid, key, place, None, city, plat, plng, TODAY)
        print(f"added {name} ({city})")


def remove() -> None:
    with db.tx() as c:
        n = c.execute("DELETE FROM users WHERE demo = 1").rowcount
    print(f"removed {n} demo traveler(s)")


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else seed()

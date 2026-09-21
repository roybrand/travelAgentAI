"""Fill the partner database with clearly-labelled DEMO businesses and deals, for showing the app.

    python scripts/seed_demo.py            # add demo deals (already approved) in Porto and Lisbon
    python scripts/seed_demo.py --remove   # delete everything this script created

Every demo partner is named "Demo · ..." and uses an @wayfinder.invalid email, so nobody can mistake them for real
businesses. Booking links point at example.com. Never run this against a database that holds real partners you
do not want mixed with demos (--remove only touches the demo accounts).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.partners import accounts, db, deals  # noqa: E402

END = date.today() + timedelta(days=60)

DEMOS = [
    ("Demo · Tasca do Rio", "restaurant", "OPO", [
        dict(title="Two-course dinner with wine", description="A two-course tasting dinner with a glass of house vinho verde, by the river.",
             category="restaurant", lat=41.1405, lng=-8.6136, price=24, reference_price=40, price_note="per person",
             tags=["food-scene"], terms="Tuesday to Thursday, booking required. Demo data."),
    ]),
    ("Demo · Cave do Douro", "tour", "OPO", [
        dict(title="Port cellar tour and tasting", description="Guided cellar tour with three ports and local cheese.",
             category="tour", lat=41.1385, lng=-8.6130, price=15, reference_price=25, price_note="per person",
             tags=["old-town"], terms="Daily 11:00 to 17:00. Demo data."),
        dict(title="Sunset river cruise", description="Fifty minutes on the Douro at golden hour, with a drink included.",
             category="activity", lat=41.1402, lng=-8.6118, price=18, reference_price=22, price_note="per person",
             terms="Departures depend on the weather. Demo data."),
    ]),
    ("Demo · Bar Luz", "bar", "OPO", [
        dict(title="Two cocktails for the price of one", description="Any two signature cocktails, 18:00 to 21:00.",
             category="bar", lat=41.1471, lng=-8.6104, price=9, reference_price=18, tags=["nightlife"],
             terms="Happy hour only, over 18s. Demo data."),
    ]),
    ("Demo · Hotel Alfama View", "hotel", "LIS", [
        dict(title="Third night free", description="Stay two nights, get the third free in a river-view double room.",
             category="hotel", lat=38.7139, lng=-9.1334, price=180, reference_price=270, price_note="for 3 nights",
             terms="Sunday to Thursday arrivals. Demo data."),
    ]),
    ("Demo · Pastelaria Sol", "restaurant", "LIS", [
        dict(title="Coffee and custard tart", description="A pastel de nata and a coffee, all day.", category="restaurant",
             lat=38.7108, lng=-9.1366, price=3, reference_price=4.5, price_note="per person", tags=["food-scene"],
             terms="Eat in only. Demo data."),
    ]),
]


def seed() -> None:
    for name, kind, city, items in DEMOS:
        email = f"{name.lower().replace(' · ', '-').replace(' ', '-')}@wayfinder.invalid"
        try:
            pid = accounts.register(name, email, "demo-password-not-secret", kind, city)["id"]
        except accounts.AccountError:
            print(f"already there: {name}")
            continue
        for it in items:
            deal = deals.DealIn(dest=city, currency="EUR", valid_to=END, url="https://example.com/demo", **it)
            deals.review(deals.create(pid, deal), True)
        print(f"added {name}: {len(items)} deal(s)")


def remove() -> None:
    with db.tx() as c:
        n = c.execute("DELETE FROM partners WHERE email LIKE '%@wayfinder.invalid'").rowcount
    print(f"removed {n} demo partner(s) and their deals")


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else seed()

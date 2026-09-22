"""Fill the partner database with 124 clearly-labelled DEMO businesses and live deals around the world.

    python scripts/seed_demo.py            # add 124 demo businesses (8 each in Tel Aviv, Berlin, Barcelona, Paris and Ibiza, 3 each in 28 more cities incl. 8 in Australia)
    python scripts/seed_demo.py --refresh  # renew expired deals and post today's "Tonight only" flash deals
    python scripts/seed_demo.py --remove   # delete every demo business and its deals

Every demo partner is named "Demo · ...", uses an @wayfinder.invalid email, and points its booking link at example.com. Deal
pictures are drawn illustrations. Deals are approved on creation so they show at once. See docs/10-alerts-and-demo-businesses.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.partners import demo_businesses  # noqa: E402

if __name__ == "__main__":
    if "--remove" in sys.argv:
        print(f"removed {demo_businesses.remove()} demo business(es)")
    elif "--refresh" in sys.argv:
        print(f"posted {demo_businesses.refresh(force=True)} new deal(s)")
    else:
        made = demo_businesses.seed(124)
        print("added", sum(made.values()), "demo businesses:", ", ".join(f"{k} {v}" for k, v in sorted(made.items())))

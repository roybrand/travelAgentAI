"""Fill Wayfinder People with 100 clearly-labelled DEMO travelers in Ibiza, Barcelona, Tel Aviv, Berlin and Paris.

    python scripts/seed_people.py              # add the demo pool (20 per city) and give everyone a request for today
    python scripts/seed_people.py --refresh    # post today's fresh requests and put the night-life crowd on real venues
    python scripts/seed_people.py --remove     # delete every demo traveler (and their plans, requests and chats)

Demo people are marked "demo" on every card, use @wayfinder.invalid emails, and have illustrated avatars, never photos of
real people. When you say hi to one it accepts and replies with canned lines, and the chat says so. They exist so the
feature can be shown before real people join. See docs/09-people-and-safety.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.social import demo_people  # noqa: E402

if __name__ == "__main__":
    if "--remove" in sys.argv:
        print(f"removed {demo_people.remove()} demo traveler(s)")
    elif "--refresh" in sys.argv:
        print(f"posted {demo_people.refresh_pool(force=True)} new request(s)")
    else:
        made = demo_people.seed(100)
        print("added", sum(made.values()), "demo travelers:", ", ".join(f"{k} {v}" for k, v in made.items()))

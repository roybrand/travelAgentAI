"""Generate AI portraits for the DEMO people, so the demo looks like a real community without using any real person's photo.

    python scripts/generate_demo_photos.py             # make a portrait for every demo profile that has none (resumable)
    python scripts/generate_demo_photos.py --limit 3   # try a few first
    python scripts/generate_demo_photos.py --remove    # delete the generated portraits (profiles fall back to drawings)

Each image is a picture of a FICTIONAL adult produced by OpenAI's image model from a written description. It is not a photo
of anyone. Every demo card is labelled "demo" and the picture carries an "AI" badge in the app. Cost: roughly one to four
US dollars for 100 images on the low-quality setting, charged to the OPENAI_API_KEY in backend/.env. Files go to
backend/data/demo_photos/ (git-ignored).
"""
import base64
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.live.http import client  # noqa: E402
from app.partners import db  # noqa: E402
from app.social import demo_people, users  # noqa: E402

DIR = config.db_path().parent / "demo_photos"
SKIN = ["very fair skin", "fair skin", "light olive skin", "olive skin", "tan skin", "warm brown skin", "deep brown skin", "dark brown skin"]
HAIR = ["short black hair", "long dark brown hair", "curly black hair", "shoulder-length wavy brown hair", "short blonde hair", "long blonde hair",
        "red hair", "a shaved head", "short grey hair", "braids", "a messy bun", "short curly brown hair", "a neat side parting"]
SETTINGS = {
    "clubber": "at night with soft neon club lighting in the background",
    "sporty": "outdoors on a sunny day, slightly flushed after exercise",
    "foodie": "at a cafe terrace in warm afternoon light",
    "culture": "in a bright gallery or old-town street",
    "nature": "outdoors by the sea or on a hiking trail",
    "social": "in a relaxed cafe, friendly expression",
}
MODELS = [
    ("gpt-image-1", {"size": "1024x1024", "quality": "low", "output_format": "webp", "output_compression": 60}, "webp"),
    ("dall-e-3", {"size": "1024x1024", "response_format": "b64_json"}, "png"),
    ("dall-e-2", {"size": "512x512", "response_format": "b64_json"}, "png"),
]
_model_index = [0]


def describe(row) -> str:
    rng = random.Random(f"photo-{row['id']}")
    age = date.today().year - row["birth_year"]
    gender = row["gender"] or rng.choice(["woman", "man"])
    who = {"woman": "woman", "man": "man", "non-binary": "androgynous person"}[gender]
    extras = []
    if gender == "man" and rng.random() < 0.35:
        extras.append(rng.choice(["a short beard", "light stubble", "a moustache"]))
    if rng.random() < 0.2:
        extras.append("glasses")
    scene = SETTINGS[demo_people._archetype_of(row)]
    return (
        f"A natural, candid smartphone portrait photo of a fictional {age}-year-old adult {who} with {rng.choice(SKIN)} and {rng.choice(HAIR)}"
        f"{' and ' + ' and '.join(extras) if extras else ''}, head and shoulders, looking at the camera with a friendly relaxed expression, "
        f"{scene}. Realistic photo, natural skin, no text, no watermark. The person is entirely imaginary."
    )


def generate(row) -> str:
    out = DIR / f"{row['id']}"
    if any(out.with_suffix(f".{e}").exists() for e in ("webp", "png")):
        return "exists"
    prompt = describe(row)
    last = None
    for attempt in range(4):
        idx = _model_index[0]
        model, params, ext = MODELS[idx]
        try:
            with client(240) as c:
                r = c.post(f"{config.openai_base_url()}/images/generations", headers={"Authorization": f"Bearer {config.openai_key()}"},
                           json={"model": model, "prompt": prompt, "n": 1, **params})
            if r.status_code in (400, 403, 404) and idx + 1 < len(MODELS):
                _model_index[0] = idx + 1     # this model is not available to the key: use the next one
                last = f"{model}: {r.status_code} {r.text[:160]}"
                continue
            if r.status_code in (429, 500, 502, 503):
                time.sleep(4 * (attempt + 1))
                last = f"{model}: {r.status_code}"
                continue
            r.raise_for_status()
            item = r.json()["data"][0]
            data = base64.b64decode(item["b64_json"])
            DIR.mkdir(parents=True, exist_ok=True)
            out.with_suffix(f".{ext}").write_bytes(data)
            return f"ok {model} {len(data) // 1024} KB"
        except Exception as exc:  # noqa: BLE001
            last = f"{model}: {type(exc).__name__}"
            time.sleep(2)
    return f"failed ({last})"


def main() -> None:
    if "--remove" in sys.argv:
        n = 0
        for p in DIR.glob("*"):
            p.unlink()
            n += 1
        print(f"removed {n} portrait(s)")
        return
    if not config.openai_key():
        sys.exit("OPENAI_API_KEY is not set in backend/.env")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    with db.tx() as c:
        rows = c.execute("SELECT * FROM users WHERE demo = 1 ORDER BY id").fetchall()
    todo = [r for r in rows if not any((DIR / f"{r['id']}.{e}").exists() for e in ("webp", "png"))]
    todo = todo[:limit] if limit else todo
    print(f"{len(todo)} portrait(s) to make of {len(rows)} demo profiles")
    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, result in zip(todo, pool.map(generate, todo)):
            done += 1
            print(f"[{done}/{len(todo)}] {row['id']} {result}", flush=True)


if __name__ == "__main__":
    main()

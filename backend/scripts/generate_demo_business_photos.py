"""Generate AI photos for demo business categories, so deal cards look attractive without using any real
business's photo.

    python scripts/generate_demo_business_photos.py             # make every category's photos (resumable)
    python scripts/generate_demo_business_photos.py --limit 3   # try a few first
    python scripts/generate_demo_business_photos.py --remove    # delete generated photos (deals fall back to drawings)

Each image is a photo of a FICTIONAL, generic venue for that category -- not a photo of any real place. Every
demo deal is labelled "Demo" and the picture carries an "AI" badge in the app. After generating, existing demo
deals are updated to point at the new photos. Cost: roughly a dollar for the default 32 images on the
low-quality setting, charged to OPENAI_API_KEY in backend/.env. Files go to
backend/data/demo_business_photos/ (git-ignored).
"""
import base64
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.live.http import client  # noqa: E402
from app.partners import db, demo_businesses  # noqa: E402

DESCRIPTIONS = {
    "restaurant": "the candlelit dining room of a stylish small restaurant, set tables, warm lighting",
    "bar": "a chic cocktail bar with a backlit shelf of bottles, warm evening light, a few empty stools",
    "party": "a lively nightclub dance floor with colourful lights and a DJ booth, blurred motion, night",
    "tour": "a small group walking through a sunny old-town cobbled street behind a guide, daytime",
    "activity": "people surfing or kayaking on a bright sunny sea, an action shot with water spray",
    "spa": "a calm spa treatment room with candles, rolled towels and soft natural light",
    "hotel": "a bright boutique hotel lobby or a hotel room with a nice view, tasteful decor",
    "car_rental": "a clean modern rental car parked in front of an airport terminal, daytime",
}
VARIANT_HINTS = ["", ", a slightly different angle", ", a different time of day", ", a different style of decor"]
MODELS = [
    ("gpt-image-1", {"size": "1024x1024", "quality": "low", "output_format": "webp", "output_compression": 60}, "webp"),
    ("dall-e-3", {"size": "1024x1024", "response_format": "b64_json"}, "png"),
    ("dall-e-2", {"size": "512x512", "response_format": "b64_json"}, "png"),
]
_model_index = [0]


def describe(kind: str, variant: int) -> str:
    hint = VARIANT_HINTS[(variant - 1) % len(VARIANT_HINTS)]
    return (
        f"A natural, realistic photo of {DESCRIPTIONS[kind]}{hint}. No people's faces in close-up, no text, "
        "no logos, no watermark. A generic, entirely fictional place, not based on any real business."
    )


def generate(job: tuple[str, int]) -> str:
    kind, variant = job
    out = demo_businesses.business_photo_dir() / f"{kind}_{variant}"
    if any(out.with_suffix(f".{e}").exists() for e in ("webp", "png")):
        return "exists"
    prompt = describe(kind, variant)
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
            out.with_suffix(f".{ext}").write_bytes(data)
            return f"ok {model} {len(data) // 1024} KB"
        except Exception as exc:  # noqa: BLE001
            last = f"{model}: {type(exc).__name__}"
            time.sleep(2)
    return f"failed ({last})"


def refresh_existing_deals() -> int:
    """Point every existing demo deal's photo at a newly generated picture, where one now exists for its
    category. Safe to call any time -- deals whose category has no generated photo keep their drawing."""
    n = 0
    with db.tx() as c:
        rows = c.execute(
            "SELECT d.id, d.category FROM deals d JOIN partners p ON p.id = d.partner_id WHERE p.email LIKE ?",
            (demo_businesses.EMAIL_PREFIX + "%@" + demo_businesses.EMAIL_DOMAIN,)).fetchall()
        for r in rows:
            c.execute("UPDATE deals SET photo_url = ? WHERE id = ?", (demo_businesses._photo_for(r["category"], r["id"]), r["id"]))
            n += 1
    return n


def main() -> None:
    if "--remove" in sys.argv:
        n = 0
        for p in demo_businesses.business_photo_dir().glob("*"):
            p.unlink()
            n += 1
        print(f"removed {n} photo(s); existing deals will fall back to the drawn illustrations")
        return
    if not config.openai_key():
        sys.exit("OPENAI_API_KEY is not set in backend/.env")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    jobs = [(kind, v) for kind in DESCRIPTIONS for v in range(1, demo_businesses.PHOTO_VARIANTS + 1)]
    todo = [j for j in jobs if not any((demo_businesses.business_photo_dir() / f"{j[0]}_{j[1]}.{e}").exists() for e in ("webp", "png"))]
    todo = todo[:limit] if limit else todo
    print(f"{len(todo)} photo(s) to make of {len(jobs)} category photos")
    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for job, result in zip(todo, pool.map(generate, todo)):
            done += 1
            print(f"[{done}/{len(todo)}] {job[0]} #{job[1]} {result}", flush=True)
    updated = refresh_existing_deals()
    print(f"updated {updated} existing demo deal(s) to use the new photos where available")


if __name__ == "__main__":
    main()

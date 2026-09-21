"""Download openly licensed photos from Wikimedia Commons for the demo UI.

Run once (needs internet); the images and a credits file are then committed/bundled so the
demo works offline:

    .venv\\Scripts\\python.exe scripts\\fetch_photos.py

For every key below it takes the first Commons search hit that is a real photograph, is
wide enough, and carries a license that allows reuse with attribution (CC BY, CC BY-SA,
CC0, public domain; NonCommercial/NoDerivatives licenses are rejected). Author and license
are written to frontend/src/data/photoCredits.json so the UI can show proper credit.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "photos"
CREDITS = ROOT / "frontend" / "src" / "data" / "photoCredits.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = "WayfinderPrototype/0.1 (roybran@gmail.com) demo photo fetch"
MIN_WIDTH = 1400
WIDTH = 1400

# key -> Commons search terms
QUERIES = {
    # Naples & Amalfi
    "NAP-hero": "Bay of Naples Vesuvius panorama",
    "NAP-amalfi": "Positano Amalfi coast",
    "NAP-capri": "Capri Faraglioni",
    "NAP-pompeii": "Pompeii forum Vesuvius",
    "NAP-centre": "Napoli centro storico vicolo",
    "NAP-path": "Sentiero degli Dei Path of the Gods",
    "NAP-vesuvius": "Mount Vesuvius crater",
    "NAP-boat": "Capri Blue Grotto boats",
    "NAP-dining": "Sorrento harbour Marina Grande",
    # Lisbon & Sintra
    "LIS-hero": "Lisbon panorama Alfama rooftops Tagus",
    "LIS-alfama": "Alfama Lisbon street",
    "LIS-belem": "Torre de Belem Lisbon",
    "LIS-sintra": "Pena Palace Sintra",
    "LIS-cascais": "Cascais bay beach",
    "LIS-surf": "Guincho beach surf",
    "LIS-tram": "Tram 28 Lisbon",
    "LIS-sail": "Tagus river sailing 25 de Abril Bridge",
    "LIS-bairro": "Bairro Alto Lisbon night",
    # Tokyo
    "TYO-hero": "Tokyo cityscape Tokyo Tower",
    "TYO-shibuya": "Shibuya Crossing",
    "TYO-asakusa": "Senso-ji Asakusa",
    "TYO-meiji": "Meiji Shrine torii",
    "TYO-hakone": "Hakone Lake Ashi Mount Fuji",
    "TYO-tsukiji": "Tsukiji outer market",
    "TYO-goldengai": "Golden Gai Shinjuku",
    "TYO-onsen": "rotenburo outdoor hot spring Japan",
    "TYO-fuji": "Mount Fuji Kawaguchiko lake",
    # Dubai
    "DXB-hero": "Dubai skyline Burj Khalifa",
    "DXB-burj": "Burj Khalifa fountain",
    "DXB-old": "Al Fahidi Dubai Creek abra",
    "DXB-palm": "Palm Jumeirah aerial",
    "DXB-abudhabi": "Sheikh Zayed Grand Mosque",
    "DXB-safari": "Dubai desert safari dunes",
    "DXB-balloon": "hot air balloons desert United Arab Emirates",
    "DXB-supercar": "Lamborghini Dubai",
    "DXB-rooftop": "Dubai Marina skyline night",
    # Generic, illustrative stays (the demo hotels are fictional; the UI labels these as illustrative)
    "stay-1": "modern hotel bedroom interior",
    "stay-2": "hotel lobby interior",
    "stay-3": "hotel rooftop swimming pool",
    "stay-4": "hotel courtyard garden terrace",
    "stay-5": "hotel room window city view",
    "stay-6": "hotel suite living room",
}

BAD_TITLE = re.compile(r"logo|map|diagram|flag|coat of arms|icon|stamp|poster|plan of|panoram(?:a)? pdf", re.I)
OK_LICENSE = re.compile(r"^(CC BY(-SA)? [\d.]+|CC0|Public domain|PD)", re.I)
BAD_LICENSE = re.compile(r"NC|ND", re.I)


def get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if binary else json.loads(data)
        except Exception as exc:  # network hiccup or 429: back off and retry
            wait = 3 * (attempt + 1)
            print(f"   retry in {wait}s ({exc})")
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def candidates(query: str):
    params = {
        "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 12,
        "gsrsearch": f"filetype:bitmap {query}", "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": WIDTH, "format": "json",
    }
    data = get(API + "?" + urllib.parse.urlencode(params))
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for page in pages:
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if info.get("mime") != "image/jpeg" or info.get("width", 0) < MIN_WIDTH:
            continue
        if BAD_TITLE.search(page["title"]) or not OK_LICENSE.match(license_name) or BAD_LICENSE.search(license_name):
            continue
        yield {
            "title": page["title"].removeprefix("File:"),
            "thumb": info["thumburl"],
            "author": strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "license": license_name,
            "license_url": meta.get("LicenseUrl", {}).get("value", ""),
            "source": info["descriptionurl"],
        }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CREDITS.parent.mkdir(parents=True, exist_ok=True)
    credits = json.loads(CREDITS.read_text(encoding="utf-8")) if CREDITS.exists() else {}
    failed = []

    for key, query in QUERIES.items():
        target = OUT_DIR / f"{key}.jpg"
        if target.exists() and key in credits:
            continue
        print(f"{key}: {query}")
        try:
            hit = next(candidates(query), None)
            if hit is None:
                print("   no suitable photo found")
                failed.append(key)
                continue
            target.write_bytes(get(hit["thumb"], binary=True))
            credits[key] = {k: hit[k] for k in ("title", "author", "license", "license_url", "source")}
            print(f"   ok: {hit['title']} ({hit['license']})")
        except Exception as exc:
            print(f"   FAILED: {exc}")
            failed.append(key)
        CREDITS.write_text(json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(1.5)

    print(f"\n{len(credits)} photos, {len(failed)} missing: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

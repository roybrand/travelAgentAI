"""The fixed vocabulary for what people like, so profiles and requests can be matched, and the optional
gender and age-band filters.

Filters are voluntary on both sides. A person chooses whether to share a gender and an age band, and can limit who is
allowed to find them. A search by gender or age only ever returns people who chose to share it. We do not offer or
apply filters by ethnicity, religion, sexuality or looks, and a request that asks for them is told so."""
import re

# tag -> (label, words that suggest it, used when no OpenAI key is set)
ACTIVITIES = {
    "nightlife": ("Nightlife", ["nightlife", "club", "clubbing", "bar hop", "dancing", "party", "drinks", "pub"]),
    "live-music": ("Live music", ["live music", "concert", "gig", "jazz", "band", "fado", "festival"]),
    "food": ("Food and dining", ["food", "dinner", "lunch", "restaurant", "tapas", "street food", "eat", "brunch"]),
    "coffee": ("Coffee and chat", ["coffee", "cafe", "tea", "chat"]),
    "wine": ("Wine and tasting", ["wine", "tasting", "cellar", "vineyard", "beer", "brewery"]),
    "museums": ("Museums", ["museum", "gallery", "exhibition"]),
    "art": ("Art and culture", ["art", "culture", "theatre", "theater", "opera", "architecture"]),
    "sightseeing": ("Sightseeing", ["sightseeing", "walking tour", "tour", "landmarks", "explore the city"]),
    "hiking": ("Hiking and nature", ["hike", "hiking", "trek", "trail", "nature", "mountain", "park"]),
    "beach": ("Beach and swimming", ["beach", "swim", "swimming", "surf", "sunbathe"]),
    "sports": ("Sports", ["football", "soccer", "tennis", "basketball", "volleyball", "padel", "sport", "gym"]),
    "running": ("Running", ["run", "running", "jog", "jogging"]),
    "cycling": ("Cycling", ["cycle", "cycling", "bike", "biking"]),
    "yoga": ("Yoga and wellness", ["yoga", "meditation", "wellness", "spa"]),
    "photography": ("Photography", ["photo", "photography", "photowalk"]),
    "language-exchange": ("Language exchange", ["language exchange", "practice spanish", "practice english", "practise", "tandem"]),
    "board-games": ("Board games", ["board game", "board games", "cards", "chess", "trivia", "quiz"]),
    "diving": ("Diving and water sports", ["dive", "diving", "snorkel", "kayak", "paddle", "sail"]),
    "shopping": ("Markets and shopping", ["market", "shopping", "flea", "vintage"]),
    "volunteering": ("Volunteering", ["volunteer", "clean-up", "charity"]),
}
LANGUAGES = ["English", "Spanish", "Portuguese", "French", "German", "Italian", "Dutch", "Arabic", "Hebrew", "Russian",
             "Turkish", "Greek", "Polish", "Chinese", "Japanese", "Korean", "Hindi", "Thai", "Vietnamese", "Indonesian"]
VIBES = ["relaxed", "adventurous", "cultural", "social", "quiet", "energetic"]
PARTS = ["morning", "afternoon", "evening", "night", "any"]

GENDERS = ["woman", "man", "non-binary"]
# label, lowest age, highest age
AGE_BANDS = {"18-24": (18, 24), "25-34": (25, 34), "35-44": (35, 44), "45-54": (45, 54), "55+": (55, 120)}

_GENDER_WORDS = {
    "woman": r"women|woman|female|females|girls?|ladies|lady",
    "man": r"men|man|male|males|guys?|boys?|gentlemen",
    "non-binary": r"non-?binary|enby",
}
# Filters we do not offer. Asking for them is answered with a note, and they are never applied.
_UNSUPPORTED = re.compile(
    r"\b(gay|straight|lesbian|bisexual|trans|jewish|muslim|christian|hindu|buddhist|atheist|religious|"
    r"(?:white|black|asian|latino|latina|arab) (?:people|guys|men|women|girls|folks)|"
    r"attractive|sexy|slim|good[- ]looking|dating|hookup|hook up)\b", re.I)
_AGE_CUE = re.compile(r"\b(age|aged|years?|yrs?|y/o|yo|old|older|younger|in their|mid|late|early|over|under|between)\b", re.I)


def clean_tags(values, allowed) -> list[str]:
    if not isinstance(values, (list, tuple)):
        values = [] if values is None else [values]
    return [v for v in dict.fromkeys(values) if v in allowed]


def age_band(birth_year: int, this_year: int) -> str | None:
    age = this_year - birth_year
    for band, (lo, hi) in AGE_BANDS.items():
        if lo <= age <= hi:
            return band
    return None


def _bands_overlapping(lo: int, hi: int) -> list[str]:
    return [b for b, (blo, bhi) in AGE_BANDS.items() if lo <= bhi and hi >= blo]


def detect_genders(text: str) -> list[str]:
    low = text or ""
    return [g for g, words in _GENDER_WORDS.items() if re.search(rf"\b(?:{words})\b", low, re.I)]


def detect_age_bands(text: str) -> list[str]:
    """Age bands a request asks for: '25-30', 'in their 30s', 'over 40', 'under 30', 'aged 28'."""
    low = (text or "").lower()
    has_cue = bool(_AGE_CUE.search(low)) or bool(detect_genders(low)) or bool(re.search(r"\b(people|someone|guys|folks)\b", low))
    bands: list[str] = []

    def add(lo: int, hi: int):
        for b in _bands_overlapping(max(lo, 18), hi):
            if b not in bands:
                bands.append(b)

    for m in re.finditer(r"\b(\d{2})\s*(?:-|–|to)\s*(\d{2})\b", low):
        lo, hi = int(m.group(1)), int(m.group(2))
        if has_cue and 18 <= lo < hi <= 99 and hi - lo <= 25:
            add(lo, hi)
    for m in re.finditer(r"\b(\d)0s\b", low):
        add(int(m.group(1)) * 10, int(m.group(1)) * 10 + 9)
    for m in re.finditer(r"\b(?:over|older than|above)\s+(\d{2})\b", low):
        add(int(m.group(1)), 120)
    for m in re.finditer(r"\b(?:under|younger than|below)\s+(\d{2})\b", low):
        add(18, int(m.group(1)) - 1)
    for m in re.finditer(r"\baged?\s+(\d{2})\b", low):
        add(int(m.group(1)), int(m.group(1)))
    return bands


def mentions_unsupported_filter(text: str) -> bool:
    return bool(_UNSUPPORTED.search(text or ""))


def mentions_personal_filter(text: str) -> bool:
    """True if the text names a gender, an age or an unsupported trait. Used to keep AI summaries about the activity only."""
    return bool(detect_genders(text) or detect_age_bands(text) or mentions_unsupported_filter(text))

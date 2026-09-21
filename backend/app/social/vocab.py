"""The fixed vocabulary for what people like, so profiles and requests can be matched. Nothing about protected
traits (gender, age, ethnicity, religion, sexuality) is ever used to filter or rank people."""
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

# Things people sometimes ask us to filter people by. We do not, and we tell them.
_SENSITIVE = re.compile(
    r"\b(men|man|male|males|women|woman|female|females|girls?|guys?|boys?|ladies|gay|straight|lesbian|trans|"
    r"younger|\d{2}\s?(?:-|to)\s?\d{2}|years? old|aged|(?:white|black|asian|latino|latina|arab) (?:people|guys|men|women|girls|folks)|jewish|muslim|"
    r"christian|hindu|atheist|religious|single (?:women|men|girls|guys|ladies)|dating|hookup|hook up|attractive|sexy|slim)\b", re.I)


def clean_tags(values, allowed) -> list[str]:
    if not isinstance(values, (list, tuple)):
        values = [] if values is None else [values]
    return [v for v in dict.fromkeys(values) if v in allowed]


def mentions_sensitive_filter(text: str) -> bool:
    return bool(_SENSITIVE.search(text or ""))

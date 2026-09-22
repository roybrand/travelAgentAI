"""Illustrated avatars for DEMO profiles. They are drawings, not photographs, and never depict a real person.

The same seed always gives the same face, so a demo profile looks the same every time. The output is a small SVG with
no scripts and no external references."""
import random

SKIN = ["#f5d0b5", "#eec1a0", "#e8b48a", "#c68642", "#a0673a", "#7a4b2a", "#4a2c1a"]
HAIR = ["#1b1b1b", "#2b1d12", "#3b2a1a", "#6b4423", "#b5651d", "#d9a441", "#c9c9c9", "#a03a2a", "#5b3a8c"]
SHIRT = ["#0f766e", "#1d4ed8", "#9333ea", "#be123c", "#b45309", "#334155", "#15803d", "#0e7490"]
STYLES = {"woman": ["long", "long", "bun", "curly", "short", "bob"], "man": ["short", "short", "curly", "bald", "cap", "short"],
          "non-binary": ["short", "long", "curly", "bun", "cap", "bob", "bald"]}


def avatar_svg(seed: int, gender: str | None) -> str:
    r = random.Random(seed * 7919 + 13)
    g = gender if gender in STYLES else r.choice(list(STYLES))
    skin, hair, shirt = r.choice(SKIN), r.choice(HAIR), r.choice(SHIRT)
    style = r.choice(STYLES[g])
    hue = r.randrange(360)
    glasses = r.random() < 0.25
    beard = g == "man" and style != "cap" and r.random() < 0.4
    earrings = g == "woman" and r.random() < 0.45
    smile = r.choice([16, 20, 24])

    back = ""
    if style == "long":
        back = f'<path d="M52 92 C44 150 60 172 100 172 C140 172 156 150 148 92 Z" fill="{hair}"/>'
    elif style == "bun":
        back = f'<circle cx="100" cy="34" r="20" fill="{hair}"/>'
    elif style == "bob":
        back = f'<path d="M54 90 C50 130 62 140 74 140 L126 140 C138 140 150 130 146 90 Z" fill="{hair}"/>'
    front = {
        "short": f'<path d="M54 84 C54 40 146 40 146 84 C136 64 64 64 54 84 Z" fill="{hair}"/>',
        "long": f'<path d="M54 90 C50 36 150 36 146 90 C138 62 62 62 54 90 Z" fill="{hair}"/>',
        "bun": f'<path d="M54 86 C54 42 146 42 146 86 C136 64 64 64 54 86 Z" fill="{hair}"/>',
        "bob": f'<path d="M52 92 C48 38 152 38 148 92 C140 60 60 60 52 92 Z" fill="{hair}"/>',
        "curly": "".join(f'<circle cx="{x}" cy="{y}" r="15" fill="{hair}"/>' for x, y in
                         [(62, 70), (80, 52), (100, 46), (120, 52), (138, 70), (56, 88), (144, 88)]),
        "bald": "",
        "cap": f'<path d="M52 78 C52 34 148 34 148 78 Z" fill="{shirt}"/><rect x="48" y="74" width="104" height="9" rx="4" fill="{shirt}"/>',
    }[style]
    extras = ""
    if beard:
        extras += f'<path d="M62 100 C64 148 136 148 138 100 C130 122 70 122 62 100 Z" fill="{hair}" opacity="0.95"/>'
    if glasses:
        extras += ('<g fill="none" stroke="#1f2937" stroke-width="3"><circle cx="82" cy="94" r="12"/><circle cx="118" cy="94" r="12"/>'
                   '<path d="M94 94 H106"/></g>')
    if earrings:
        extras += '<circle cx="54" cy="108" r="4" fill="#f5c76a"/><circle cx="146" cy="108" r="4" fill="#f5c76a"/>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200" role="img" aria-label="Illustrated avatar">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl({hue} 60% 42%)"/>'
        f'<stop offset="1" stop-color="hsl({(hue + 60) % 360} 65% 24%)"/></linearGradient></defs>'
        '<rect width="200" height="200" fill="url(#g)"/>'
        f'{back}'
        f'<ellipse cx="100" cy="206" rx="70" ry="52" fill="{shirt}"/>'
        f'<rect x="88" y="128" width="24" height="30" rx="8" fill="{skin}"/>'
        f'<ellipse cx="54" cy="98" rx="7" ry="11" fill="{skin}"/><ellipse cx="146" cy="98" rx="7" ry="11" fill="{skin}"/>'
        f'<ellipse cx="100" cy="92" rx="46" ry="54" fill="{skin}"/>'
        f'{front}'
        '<circle cx="82" cy="94" r="4.5" fill="#1f2937"/><circle cx="118" cy="94" r="4.5" fill="#1f2937"/>'
        '<path d="M72 80 Q82 74 92 80 M108 80 Q118 74 128 80" fill="none" stroke="#1f2937" stroke-width="3" stroke-linecap="round" opacity="0.6"/>'
        '<path d="M100 98 Q96 112 102 114" fill="none" stroke="#00000033" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M{100 - smile} 122 Q100 {132 + smile // 4} {100 + smile} 122" fill="none" stroke="#7f1d1d" stroke-width="3.5" stroke-linecap="round"/>'
        f'{extras}</svg>'
    )

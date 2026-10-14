#!/usr/bin/env python3
"""
caption.py - lint an Instagram caption and show exactly what the feed shows
before the "... more".

Instagram gives a caption about 125 characters in the feed and hides the rest
behind a tap. Almost every caption that fails, fails there: the hook is in
sentence three, or the first line is a greeting, or the whole thing opens on a
hashtag. This prints the visible window as a box so you can read it the way a
scrolling stranger does, then checks the eight things that are worth checking.

The 125-character cut is an approximation. The real number moves with the
device, the font size and where your line breaks fall, which is exactly why
you want a margin rather than a caption engineered to end at 125. Change it
with --truncate if you want to test a tighter one.

English and French. --lang auto (the default) reads the caption and picks. In
French the asks are the French ones ("commente CONTRAT", "lien en bio",
"abonne-toi"), hashtags keep their accents (#éducation), "18 000 €" counts as
one number, and #pourtoi joins #fyp on the list of tags that describe nothing.

Usage
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "proposal software,client contract"
  pbpaste | python3 caption.py -
  python3 caption.py caption.txt --json
  python3 caption.py legende.txt --lang fr --keywords "contrat client,tarifs freelance"
"""

import argparse
import json
import os
import re
import sys
import textwrap

LIMIT = 2200             # Instagram's hard caption limit.
TRUNCATE = 125           # Roughly where the feed cuts to "... more".
HASHTAG_LIMIT = 5        # Instagram's cap per post or reel since 18 Dec 2025,
                         # down from 30. Announced by the @Creators account:
                         # "using fewer (up to 5) more targeted hashtags,
                         # rather than many generic ones, can improve both your
                         # content's performance and people's experience".

HASHTAG_RE = re.compile(r"(?:^|\s)(#[A-Za-z0-9_]+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[A-Za-z0-9_.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:com|co|io|net|org|ai|app)/\S*",
                     re.IGNORECASE)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-⇿️]")
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)

ASKS = [
    (re.compile(r"(?i)\bcomment (?:the word |\")?[A-Z0-9]{2,}\b"), "comment a keyword"),
    (re.compile(r"(?i)\b(?:dm|message) me\b"), "DM me"),
    (re.compile(r"(?i)\bsave (?:this|it)\b"), "save this"),
    (re.compile(r"(?i)\bshare (?:this|it)\b"), "share this"),
    (re.compile(r"(?i)\bfollow (?:me|for)\b"), "follow"),
    (re.compile(r"(?i)\blink in (?:my )?bio\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:swipe|tap) (?:through|left|right|for|to)\b"), "swipe or tap"),
    (re.compile(r"(?i)\btell me\b|\bwhat would you\b|\bwhich one\b"), "answer a question"),
]

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily"}

# French. Instagram hashtags take accents, so a tag is any run of letters.
# A keyword ask is only a keyword when it is written in capitals, which is how
# every French creator writes it ("Commente GUIDE"), so the keyword part is
# case-sensitive even though the verb is not.
HASHTAG_RE_FR = re.compile(r"(?:^|\s)(#\w+)")
CONCRETE_RE_FR = re.compile(r"[$€]\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]{2,}\b",
                            re.MULTILINE)
THOUSANDS_FR = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")
ASKS_FR = [
    (re.compile(r"(?i:\bcommente(?:z)?)\s+(?:(?i:le mot)\s+)?[«\"“]?\s?[A-ZÀ-ÖØ-Þ0-9]{2,}\b"),
     "comment a keyword"),
    # "je te l'envoie en DM" is how the keyword gets delivered, not a second
    # ask, so only the imperative counts.
    (re.compile(r"(?i)\b(?:écris|écrivez|envoie|envoyez)-moi\b|\b(?:dm|mp|message)[- ]moi\b"),
     "DM me"),
    (re.compile(r"(?i)\b(?:enregistre|enregistrez|sauvegarde|sauvegardez|garde|gardez)"
                r"(?:-le|-la|-les| ce| cette| ça| ces)\b"), "save this"),
    (re.compile(r"(?i)\bpartage(?:z)?(?:-le|-la| ce| cette| ça| à)\b"), "share this"),
    (re.compile(r"(?i)\b(?:abonne-toi|abonnez-vous|suis-moi|suivez-moi)\b"), "follow"),
    (re.compile(r"(?i)\blien (?:en |dans (?:ma |la |mon )?)bio\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:swipe|glisse|glissez|fais défiler|faites défiler)\b"), "swipe or tap"),
    (re.compile(r"(?i)\b(?:dis|dites)-moi\b|\b(?:tu|vous) en pens(?:es|ez) quoi\b"
                r"|\b(?:lequel|laquelle|lesquels)\b|\btu ferais quoi\b|\bvous feriez quoi\b"),
     "answer a question"),
]
FILLER_TAGS_FR = FILLER_TAGS | {
    "#pourtoi", "#pourtoii", "#pourtoiii", "#pourtoipage", "#pourvous", "#tendance",
    "#tendances", "#abonnetoi", "#abonnezvous", "#jaime", "#instafrance", "#reelsfrance",
    "#viralfrance", "#explorer", "#instaquebec", "#reelsquebec",
}

FR_MARKERS = {
    "le", "la", "les", "des", "du", "de", "une", "et", "est", "sont", "pas",
    "que", "qui", "dans", "pour", "avec", "sur", "ce", "cette", "ces", "je",
    "tu", "il", "elle", "nous", "vous", "mon", "ma", "mes", "ton", "ta", "tes",
    "notre", "votre", "leur", "au", "aux", "mais", "ou", "donc", "ça", "très",
    "tout", "tous", "comme", "fait", "être", "avoir", "j", "qu", "ai", "parce",
    "l", "c", "n", "ne", "me", "te", "se", "moi", "toi", "par", "sans", "chez",
    "aussi", "contre", "quoi", "pourquoi", "comment", "rien", "jamais",
}
EN_MARKERS = {
    "the", "and", "is", "are", "was", "were", "not", "that", "which", "in",
    "for", "with", "this", "these", "you", "your", "he", "she", "we", "they",
    "my", "his", "her", "our", "their", "of", "to", "it", "but", "or", "so",
    "just", "like", "be", "have", "do", "what", "how", "because", "i",
}


def detect_lang(text):
    """'fr' when the text reads as French, else 'en'.

    French function words, plus lower-case words carrying a French accent
    (arrête, ça, déjà). Capitalised ones are left out so "I moved to Montréal"
    stays English. Ties and silence go to English.
    """
    toks = re.findall(r"[^\W\d_]+", text)
    low = [t.lower() for t in toks]
    fr = sum(1 for t in low if t in FR_MARKERS)
    fr += sum(1 for t in toks if t[0].islower() and t not in FR_MARKERS
              and re.search(r"[àâçéèêëîïôûùüœ]", t))
    en = sum(1 for t in low if t in EN_MARKERS)
    return "fr" if fr > en else "en"


def resolve_lang(choice, text):
    """--lang beats IG_LANG beats reading the text. fr-CA and fr_FR are fr."""
    choice = (choice or os.environ.get("IG_LANG") or "auto").lower()[:2]
    return choice if choice in ("en", "fr") else detect_lang(text)


def visible_window(text, cut):
    """What the feed shows. Instagram cuts mid-word, so this does too."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  WHAT THE FEED SHOWS", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "... more" if truncated else "(whole caption fits)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def analyse(text, cut=TRUNCATE, keywords=None, lang="en"):
    fr = lang == "fr"
    hashtag_re = HASHTAG_RE_FR if fr else HASHTAG_RE
    concrete_re = CONCRETE_RE_FR if fr else CONCRETE_RE
    ask_list = ASKS_FR if fr else ASKS
    filler_tags = FILLER_TAGS_FR if fr else FILLER_TAGS
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = hashtag_re.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    asks = [name for pattern, name in ask_list if pattern.search(stripped)]
    filler = [t for t in tags if t.lower() in filler_tags]
    # The concreteness check reads "18 000 €" as one number, not two.
    concrete_window = THOUSANDS_FR.sub("", window) if fr else window
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    add("LENGTH", "FAIL" if chars > LIMIT else "PASS",
        f"{chars} / {LIMIT} characters" + (f", {chars - LIMIT} over the limit"
                                           if chars > LIMIT else ""))

    if not first_line:
        add("FIRST LINE", "FAIL", "the caption opens on a blank line")
    elif first_line.startswith("#") or first_line.startswith("@"):
        add("FIRST LINE", "FAIL",
            "opens on a hashtag or a mention, which is the one position worth a sentence")
    elif len(first_line) > cut:
        add("FIRST LINE", "WARN",
            f"{len(first_line)} characters, so it gets cut at {cut} mid-thought. "
            "Fine if the cut is a cliffhanger, bad if it is a subordinate clause")
    else:
        add("FIRST LINE", "PASS", f"{len(first_line)} characters, lands whole")

    add("HOOK IS CONCRETE", "PASS" if concrete_re.search(concrete_window) else "WARN",
        f"{len(concrete_re.findall(concrete_window))} number(s) or name(s) in the visible window"
        + ("" if concrete_re.search(concrete_window) else " - nothing checkable before the tap"))

    if len(tags) > HASHTAG_LIMIT:
        add("HASHTAGS", "FAIL", f"{len(tags)} tags, over Instagram's cap of {HASHTAG_LIMIT}. "
                                "Tags past the fifth do not count and the block reads as old")
    elif len(tags) == HASHTAG_LIMIT and filler:
        add("HASHTAGS", "WARN", f"{len(tags)} tags, at the cap, and "
                                f"{len(filler)} of them generic. Spend the five on topics")
    elif filler:
        add("HASHTAGS", "WARN", f"{len(tags)} tags, {len(filler)} of them generic "
                                f"({', '.join(filler[:3])}). Those describe nothing")
    else:
        add("HASHTAGS", "PASS", f"{len(tags)} tag(s)" + (f": {' '.join(tags)}" if tags else ""))

    if not tags:
        add("TAG PLACEMENT", "PASS", "no tags to place")
    elif any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        add("TAG PLACEMENT", "WARN", "a hashtag is inside the visible window, "
                                     "spending feed space on a label")
    else:
        add("TAG PLACEMENT", "PASS", "tags are below the fold")

    add("LINKS", "WARN" if links else "PASS",
        f"{len(links)} link(s) in the caption, and captions are not clickable. "
        f"Move it to the bio or the DM" if links else "no dead links in the body")

    if len(asks) == 1:
        add("ONE ASK", "PASS", f"one call to action: {asks[0]}")
    elif not asks:
        add("ONE ASK", "WARN", "no call to action. Decide what this post is for")
    else:
        add("ONE ASK", "WARN", f"{len(asks)} asks ({', '.join(asks)}). "
                               "Two asks is the same as none")

    density = len(emoji) * 100 / max(chars, 1)
    add("EMOJI", "WARN" if density > 4 else "PASS",
        f"{len(emoji)} emoji, {density:.1f} per 100 characters"
        + (" - reads as decoration" if density > 4 else ""))

    if keywords:
        low = stripped.lower()
        found = [k for k in keywords if k.lower() in low]
        missing = [k for k in keywords if k.lower() not in low]
        in_window = [k for k in found if k.lower() in window.lower()]
        status = "PASS" if not missing else ("WARN" if found else "FAIL")
        add("SEARCH TERMS", status,
            f"{len(found)}/{len(keywords)} present"
            + (f", {len(in_window)} in the visible window" if found else "")
            + (f". Missing: {', '.join(missing)}" if missing else ""))

    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    verdict = "FIX" if fails else ("REVIEW" if warns else "READY")

    return {
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks,
        "checks": checks, "verdict": verdict,
        **({"lang": lang} if fr else {}),
    }


def render(a, out=sys.stdout):
    head = (f"CAPTION LINT  ·  {a['characters']} / {a['limit']} chars  ·  "
            f"{len(a['hashtags'])} hashtags  ·  {len(a['asks'])} ask(s)"
            + ("  ·  français" if a.get("lang") == "fr" else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {c['status']:<5} {c['check']:<17} {c['detail']}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  VERDICT  {a['verdict']}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Lint an Instagram caption.")
    ap.add_argument("input", nargs="?", default="-", help="caption file, or - for stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"characters shown before '... more' (default {TRUNCATE})")
    ap.add_argument("--keywords", default="", help="comma-separated terms you want to be found for")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", choices=["auto", "en", "fr"],
                    help="language of the caption (default: IG_LANG, else read from the text)")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    lang = resolve_lang(args.lang, raw)
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","), lang=lang)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0 if a["verdict"] == "READY" else 1)


if __name__ == "__main__":
    main()

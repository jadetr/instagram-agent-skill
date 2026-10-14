#!/usr/bin/env python3
"""
beats.py - turn a Reel script into a timed beat sheet before you record it.

Estimates how long each line takes to say, stacks them into timecodes, and
flags the four things that kill a Reel in the edit: a hook that runs past the
three-second mark, a beat long enough for the viewer to leave, a run of lines
with nothing concrete in them, and a total length that does not match what you
said you were making.

The timings are an estimate from word count at a words-per-minute rate. They
are close enough to plan an edit and not a substitute for recording it. Set
your own rate with --wpm once you have timed yourself reading a script out
loud: most people land between 150 and 200, and the default here is 165.

English and French. --lang auto (the default) reads the script and picks. In
French the default rate is 175 wpm, "18 000 €" is one spoken word-group rather
than two, French function words are ignored when checking the loop, and an
elided word still counts ("l'erreur" echoes "erreur").

Usage
  python3 beats.py script.txt
  python3 beats.py script.txt --target 30
  python3 beats.py script.txt --wpm 185 --target 45
  pbpaste | python3 beats.py -
  python3 beats.py script.txt --json
  python3 beats.py script_fr.txt --lang fr --target 30
"""

import argparse
import json
import os
import re
import sys

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
SENT_RE = re.compile(r"[^.!?]+[.!?]*")
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "you", "your", "i", "my", "me", "we", "our", "they", "them", "he", "she",
    "so", "just", "not", "no", "do", "did", "does", "have", "has", "had",
    "will", "can", "at", "as", "by", "from", "out", "up", "off", "one", "all",
}

# French.
WORD_RE_FR = re.compile(r"[\w$%€'’-]+(?:,\d+)?")
CONCRETE_RE_FR = re.compile(r"[$€]\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]{2,}\b",
                            re.MULTILINE)
THOUSANDS_FR = re.compile(r"(?<=\d)[ \u00a0\u202f.](?=\d{3}(?!\d))")
ELISION_FR = re.compile(r"^(?:[ldjmntsc]|qu|lorsqu|puisqu|jusqu)['’]")
STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "mais",
    "si", "à", "au", "aux", "en", "dans", "sur", "pour", "par", "avec", "que",
    "qui", "ce", "cette", "ces", "ça", "c'est", "est", "sont", "était", "être",
    "a", "ai", "as", "ont", "avoir", "tu", "te", "toi", "ton", "ta", "tes",
    "vous", "votre", "vos", "je", "me", "moi", "mon", "ma", "mes", "nous",
    "notre", "nos", "on", "il", "elle", "ils", "elles", "lui", "leur", "y",
    "ne", "pas", "plus", "donc", "alors", "juste", "fait", "faire", "tout",
    "tous", "même", "comme", "très", "c", "l", "d", "j", "qu", "n", "s", "€", "$", "%",
}
DEFAULT_WPM = {"en": 165, "fr": 175}

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


HOOK_WINDOW = 3.0        # seconds. Past this, the thumb has already decided.
MAX_BEAT = 4.0           # seconds on one idea with no change on screen.
ABSTRACT_RUN = 3         # beats in a row with nothing checkable in them.


def words(text, lang="en"):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    if lang == "fr":
        return WORD_RE_FR.findall(THOUSANDS_FR.sub("", text))
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def loop_words(text, lang="en"):
    """The words that can carry a loop: no function words, elision removed."""
    if lang == "fr":
        out = set()
        for w in words(text, lang):
            w = ELISION_FR.sub("", w.lower().replace("’", "'")).strip("'")
            if w and w not in STOPWORDS_FR:
                out.add(w)
        return out
    return {w.lower() for w in words(text) if w.lower() not in STOPWORDS}


def pretty(token, lang="en"):
    """Put the thousands separator back for display. French uses a space."""
    return re.sub(r"(\d)(?=(\d{3})+$)", r"\1 " if lang == "fr" else r"\1,", token)


def tc(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def split_beats(raw, wps, lang="en"):
    """One line is one beat, unless a line is too long to be one."""
    beats = []
    for line in [l.strip() for l in raw.splitlines()]:
        if not line:
            continue
        if len(words(line, lang)) / wps <= MAX_BEAT * 1.5:
            beats.append(line)
            continue
        # Long paragraph: break it at sentence ends so the timings mean
        # something, and let the report say it was split.
        parts = [p.strip() for p in SENT_RE.findall(line) if p.strip()]
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip()
            if buf and len(words(candidate, lang)) / wps > MAX_BEAT:
                beats.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            beats.append(buf)
    return beats


def analyse(raw, wpm=None, target=None, lang="en"):
    wpm = wpm or DEFAULT_WPM[lang]
    wps = wpm / 60.0
    beats = split_beats(raw, wps, lang)
    if not beats:
        return None
    concrete_re = CONCRETE_RE_FR if lang == "fr" else CONCRETE_RE

    rows, clock = [], 0.0
    for i, text in enumerate(beats):
        n = len(words(text, lang))
        dur = n / wps
        rows.append({
            "n": i + 1,
            "start": round(clock, 2),
            "dur": round(dur, 2),
            "words": n,
            "text": text,
            "concrete": len(concrete_re.findall(THOUSANDS_FR.sub("", text) if lang == "fr" else text)),
            "label": "",
            "flags": [],
        })
        clock += dur
    total = clock

    # Label the structural positions a Reel is actually built around.
    for r in rows:
        if r["n"] == 1 or r["start"] + r["dur"] <= HOOK_WINDOW:
            r["label"] = "HOOK"
    rows[-1]["label"] = "CTA" if rows[-1]["label"] != "HOOK" else "HOOK/CTA"
    half = total / 2
    for r in rows:
        if not r["label"] and r["start"] <= half < r["start"] + r["dur"]:
            r["label"] = "MID"

    notes = []
    if rows[0]["dur"] > HOOK_WINDOW:
        rows[0]["flags"].append(f"hook runs {rows[0]['dur']:.1f}s, past the {HOOK_WINDOW:.0f}s mark")
        notes.append(f"Beat 1 takes {rows[0]['dur']:.1f}s to say. Cut it to "
                     f"{int(HOOK_WINDOW * wps)} words or fewer, or the hook lands after "
                     "the decision has been made.")
    if rows[0]["concrete"] == 0:
        notes.append("Beat 1 has no number and no name in it. Hooks without something "
                     "checkable are the ones that get scrolled.")

    for r in rows:
        if r["dur"] > MAX_BEAT:
            r["flags"].append(f"{r['dur']:.1f}s on one beat")
    long_beats = [r["n"] for r in rows if r["dur"] > MAX_BEAT]
    if long_beats:
        notes.append(f"Beat(s) {', '.join(map(str, long_beats))} run past {MAX_BEAT:.0f}s. "
                     "Either split the line or change what is on screen inside it. "
                     "A static frame is where people leave.")

    run, start = 0, None
    for r in rows:
        if r["concrete"] == 0:
            run += 1
            start = start if start is not None else r["n"]
            if run == ABSTRACT_RUN:
                notes.append(f"Beats {start}-{r['n']} have nothing concrete in them. "
                             "Put a number, a name or a price in one of them.")
        else:
            run, start = 0, None

    # Does the last line hand you back to the first one?
    first = loop_words(rows[0]["text"], lang)
    last = loop_words(rows[-1]["text"], lang)
    loop = sorted(pretty(w, lang) for w in first & last)
    if loop:
        notes.append(f"Loops: the last beat repeats \"{', '.join(loop[:3])}\" from the hook. "
                     "Second watches are free reach.")
    else:
        notes.append("No loop. The last beat shares no word with the hook, so the video "
                     "ends flat. Echoing one word from beat 1 is the cheapest replay you get.")

    if target:
        delta = total - target
        if abs(delta) <= target * 0.1:
            notes.append(f"Length is on target ({total:.1f}s against {target}s).")
        elif delta > 0:
            notes.append(f"{delta:.1f}s over target. Cut about {int(delta * wps)} words.")
        else:
            notes.append(f"{-delta:.1f}s under target. Either add {int(-delta * wps)} words "
                         "or shoot it short. Short is usually right.")

    return {
        **({"lang": lang} if lang != "en" else {}),
        "wpm": wpm, "target": target,
        "total_seconds": round(total, 2),
        "total_words": sum(r["words"] for r in rows),
        "beats": rows,
        "notes": notes,
    }


def render(a, out=sys.stdout):
    head = (f"BEAT SHEET  ·  {a['total_words']} words  ·  ~{a['total_seconds']:.1f}s "
            f"at {a['wpm']} wpm" + (f"  ·  target {a['target']}s" if a["target"] else "")
            + ("  ·  français" if a.get("lang") == "fr" else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for r in a["beats"]:
        label = f"{r['label']:<8}" if r["label"] else " " * 8
        print(f"  {tc(r['start'])}  {r['dur']:4.1f}s  {label}{r['text']}", file=out)
        for f in r["flags"]:
            print(f"  {'':>6}  {'':>5}  {'':<8}^ {f}", file=out)
    print("-" * max(len(head), 72), file=out)
    for n in a["notes"]:
        print(f"  - {n}", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Time a Reel script into a beat sheet.")
    ap.add_argument("input", nargs="?", default="-", help="script file, or - for stdin")
    ap.add_argument("--wpm", type=float, help="speaking rate (default 165, or 175 in French)")
    ap.add_argument("--target", type=float, help="target length in seconds")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", choices=["auto", "en", "fr"],
                    help="language of the script (default: IG_LANG, else read from the text)")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, wpm=args.wpm, target=args.target, lang=resolve_lang(args.lang, raw))
    if not a:
        print("empty script", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0)


if __name__ == "__main__":
    main()

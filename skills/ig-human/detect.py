#!/usr/bin/env python3
"""
detect.py - a five-check panel that scores how machine-written a draft looks.

What this is:  five local heuristics modelled on the signals public AI
detectors actually measure - sentence-length variation, concreteness, stock
vocabulary, typographic fingerprint, and voice. Every score is computed on
your machine from the text alone. Nothing is uploaded.

What this is NOT:  GPTZero, Originality, Copyleaks, Winston or Turnitin.
It does not call their APIs and it cannot promise their verdict. It catches
the things they all key on, which is why fixing them tends to move their
numbers too - but the only honest claim is the one on this line.

Each check returns a HUMAN score from 0 to 100. Higher is better.

English and French. --lang auto (the default) reads the draft and picks. In
French the five checks measure the same things with French evidence: "ça",
"c'est pas", "t'as" and the dropped "ne" stand in for contractions, numbers
are read with French separators (18 000 €), the lexicon is the "fr" block of
slop.json, a non-breaking space before ; : ! ? is correct French typography
and is not counted as a fingerprint, and mixing tu and vous counts as a tell.

Usage
  python3 detect.py draft.txt
  pbpaste | python3 detect.py -
  python3 detect.py draft.txt --json
  python3 detect.py before.txt after.txt      # compare two drafts
  python3 detect.py brouillon.txt --lang fr
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-z']+")
CONTRACTIONS = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)
PRONOUNS = re.compile(r"\b(i|me|my|mine|we|us|our|you|your)\b", re.IGNORECASE)
NUMBERS = re.compile(r"\b\d[\d,.]*%?\b|\$\d")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)

# French. Elisions (l', j', qu') are grammar, not informality, so they are part
# of the word here. What marks spoken French in writing is "ça" over "cela",
# "t'as", "y'a", and the "ne" that nobody says: "c'est pas", "je sais pas".
WORD_RE_FR = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
INFORMAL_FR = re.compile(
    r"\b(?:ça|ouais|bah|pis|chui)\b"
    r"|\b(?:t['’](?:as|es|étais|avais)|y['’]a|j['’]sais|j['’]suis)\b"
    r"|\b(?:c['’]est|j['’]ai|t['’]as|t['’]es|y['’]a|il y a|faut) pas\b"
    r"|\b(?:je|tu|il|elle|on|ils|elles)\s+(?!ne\b|n['’])[^\W\d_'’]+\s+(?:pas|jamais|plus rien)\b",
    re.IGNORECASE)
PRONOUNS_FR = re.compile(
    r"\b(?:je|me|moi|mon|ma|mes|nous|notre|nos|on|tu|te|toi|ton|ta|tes|vous|votre|vos)\b"
    r"|\b[jmt]['’](?=[^\W\d_])", re.IGNORECASE)
NUMBERS_FR = re.compile(r"\b\d[\d,.]*(?:\s?%)?|[$€]\s?\d")
PROPER_FR = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]{2,}\b", re.MULTILINE)
THOUSANDS_FR = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")
# A thin or non-breaking space before ; : ! ? » and after « is how French is
# typeset. Not a fingerprint in French, so not counted.
NBSP_FR_OK = re.compile(r"[\u00a0\u202f\u2009](?=[;:!?»])|(?<=«)[\u00a0\u202f\u2009]")

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


def lexicon_for(lex, lang):
    if lang == "fr" and "fr" in lex:
        return dict(lex, words=lex["fr"]["words"], phrases=lex["fr"]["phrases"],
                    structures=lex["fr"]["structures"])
    return lex


def term_re(find, lang="en"):
    if lang != "fr":
        return re.compile(r"\b" + re.escape(find).replace(r"\ ", r"\s+") + r"\b",
                          re.IGNORECASE)
    body = re.escape(find)
    body = re.sub(r"\\ (?=\\\?|!|;|:)", r"\\s*", body)
    body = body.replace(r"\ ", r"\s+").replace("'", "['’]")
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Map value onto 0-100 where `human` -> 100 and `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text, lang="en"):
    return (WORD_RE_FR if lang == "fr" else WORD_RE).findall(text)


def check_burstiness(text):
    """Humans vary sentence length hard. Models write even."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "too short to judge"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=0.70, machine=0.22)
    return score, f"variation {cv:.2f} across {len(lens)} sentences (want 0.55+)"


def check_specificity(text, lang="en"):
    """Numbers, names and concrete nouns. Slop is abstract."""
    w = words(text, lang)
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    if lang == "fr":
        # French writes 18 000 with a space, and capitalises less: no capitals
        # on months, days or nationalities, so the bar for names is lower.
        flat = THOUSANDS_FR.sub("", text)
        hits = len(NUMBERS_FR.findall(flat)) + len(set(PROPER_FR.findall(flat)))
        score = scale(hits * per100, human=5.0, machine=0.5)
    else:
        hits = len(NUMBERS.findall(text)) + len(set(PROPER.findall(text)))
        score = scale(hits * per100, human=6.0, machine=0.5)
    density = hits * per100
    return score, f"{hits} concrete markers, {density:.1f} per 100 words (want 4+)"


def check_slop(text, lex, lang="en"):
    """Stock vocabulary density against the lexicon."""
    w = words(text, lang)
    if not w:
        return 50.0, "empty"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        pattern = term_re(entry["find"], lang)
        n = len(pattern.findall(text))
        if n:
            hits += n
            found.append(entry["find"])
    density = hits * 100 / len(w)
    score = scale(density, human=0.0, machine=4.0)
    detail = f"{hits} stock terms, {density:.1f} per 100 words"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text, lang="en"):
    """Characters a phone keyboard does not produce."""
    if lang == "fr":
        text = NBSP_FR_OK.sub(" ", text)
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf")
    em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    total = invisible * 4 + em * 2 + curly + ellip + nbsp
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=0.0, machine=12.0)
    detail = (f"{invisible} invisible, {em} em dash, {curly} curly quote, "
              f"{ellip} ellipsis, {nbsp} hard space")
    return score, detail


def check_voice(text, lex, lang="en"):
    """Contractions, person, and the shapes models default to."""
    w = words(text, lang)
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    if lang == "fr":
        contractions = len(INFORMAL_FR.findall(text)) * per100
        person = len(PRONOUNS_FR.findall(text)) * per100
        person_scale = dict(human=10.0, machine=2.0)   # French grammar needs more pronouns
    else:
        contractions = len(CONTRACTIONS.findall(text)) * per100
        person = len(PRONOUNS.findall(text)) * per100
        person_scale = dict(human=8.0, machine=1.0)
    tells = 0
    names = []
    for s in lex["structures"]:
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    if lang == "fr":
        tu = len(re.findall(r"(?i)\b(?:tu|toi|ton|ta|tes)\b", text))
        vous = len(re.findall(r"(?i)\b(?:vous|votre|vos)\b", text))
        if tu and vous:
            tells += 1
            names.append("tu-vous-mix")
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3 and statistics.pstdev(bullets) < 1.6)
    score = (scale(contractions, human=3.0, machine=0.0) * 0.35
             + scale(person, **person_scale) * 0.35
             + clamp(100 - tells * 22) * 0.30)
    if uniform:
        score -= 12
        names.append("uniform-bullets")
    detail = (f"{contractions:.1f} {'spoken-French markers' if lang == 'fr' else 'contractions'}, "
              f"{person:.1f} personal pronouns per 100 words, {tells} structural tell(s)")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["BURSTINESS", "SPECIFICITY", "SLOP DENSITY", "FINGERPRINT", "VOICE"]


def run(text, lex, lang="en"):
    lex = lexicon_for(lex, lang)
    results = {}
    results["BURSTINESS"] = check_burstiness(text)
    results["SPECIFICITY"] = check_specificity(text, lang)
    results["SLOP DENSITY"] = check_slop(text, lex, lang)
    results["FINGERPRINT"] = check_fingerprint(text, lang)
    results["VOICE"] = check_voice(text, lex, lang)
    scores = [results[c][0] for c in CHECKS]
    # The weakest check drags the verdict: a detector only needs one signal.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4
    verdict = "PASS" if overall >= 70 and min(scores) >= 55 else (
        "REVIEW" if overall >= 50 else "FLAGGED")
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout, lang="en"):
    title = ("AI DETECTION PANEL" + (f"  -  {label}" if label else "")
             + ("  ·  français" if lang == "fr" else ""))
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HUMAN SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != "PASS":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest signal: {weakest}. Fix that first.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Score how machine-written a draft looks.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("compare", nargs="?", help="second file, to show before/after")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lexicon", default=LEX)
    ap.add_argument("--lang", choices=["auto", "en", "fr"],
                    help="language of the draft (default: IG_LANG, else read from the text)")
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    # Both sides of a before/after are judged in the same language, the
    # first draft's, or the delta would compare two different rulers.
    lang = resolve_lang(args.lang, targets[0][1])
    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex, lang)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })
        if lang != "en":
            payload[-1]["lang"] = lang

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2,
                         ensure_ascii=lang == "en"))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex, lang)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None,
               lang=lang)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()

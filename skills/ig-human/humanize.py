#!/usr/bin/env python3
"""
humanize.py - strip the machine fingerprint out of a draft.

Three passes, in this order:

  1. INVISIBLE   delete or normalise the characters a human keyboard never
                 produces: zero-width joiners, word joiners, soft hyphens,
                 BOMs, Unicode tag characters, non-breaking and narrow spaces.
                 These survive copy-paste and are the most mechanical tell in
                 any generated text.
  2. TYPOGRAPHIC em dash -> comma, en dash -> hyphen, curly quotes -> straight,
                 ellipsis -> three dots, bullet -> hyphen.
  3. LEXICAL     replace the slop lexicon in slop.json with plain words,
                 preserving capitalisation and leaving URLs untouched.

English and French. --lang auto (the default) reads the draft and picks; it
only says French when the text clearly is, so English drafts run exactly as
they always did. In French the lexicon is the "fr" block of slop.json, elision
is repaired after a swap (de + améliorer -> d'améliorer), the writer's own
spacing before ; ! ? is kept rather than stripped, and mixing tu and vous gets
flagged. Set IG_LANG=fr to make French the default for every script.

Structural tells (rule-of-three, "not just X, it's Y", hashtag walls) are
REPORTED, never auto-rewritten - rewriting a sentence's shape needs judgement,
so that is the model's job, not a regex's.

Usage
  python3 humanize.py draft.txt
  python3 humanize.py draft.txt --report
  pbpaste | python3 humanize.py - --report
  python3 humanize.py draft.txt --json
  python3 humanize.py draft.txt -o clean.txt
  python3 humanize.py brouillon.txt --lang fr --report
"""

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")

# Function words that only one of the two languages uses. Counting them is
# crude and it is enough: a caption is either clearly French or it is not, and
# anything ambiguous stays English, which is what every script did before.
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
FR_VOWELS = "aeiouyàâäéèêëîïôöùûüœæ"
FR_CONNECTIVES = r"aussi|donc|pourtant|en plus|bref|finalement"


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


def load_lexicon(path=LEX):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lexicon_for(lex, lang):
    """The English lists, or the same shape with the French ones swapped in.

    Invisible characters and typography are shared: a zero-width space is the
    same artefact in any language.
    """
    if lang == "fr":
        if "fr" not in lex:
            print("note: this lexicon has no \"fr\" block, using the English one.",
                  file=sys.stderr)
            return lex
        return dict(lex, words=lex["fr"]["words"], phrases=lex["fr"]["phrases"],
                    structures=lex["fr"]["structures"])
    return lex


def term_re(find, lang="en"):
    """One lexicon entry as a regex. Spaces match any run of whitespace."""
    if lang != "fr":
        return re.compile(r"\b" + re.escape(find).replace(r"\ ", r"\s+") + r"\b",
                          re.IGNORECASE)
    # French entries can end on punctuation ("de plus,") where \b fails, the
    # space before ? is optional because Quebec and phones often drop it, and
    # an apostrophe matches both the straight and the curly one.
    body = re.escape(find)
    body = re.sub(r"\\ (?=\\\?|!|;|:)", r"\\s*", body)
    body = body.replace(r"\ ", r"\s+").replace("'", "['’]")
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def spaced_punctuation(text):
    """Does this writer put a space before ; ! ? (France) or not (Quebec, phones)."""
    spaced = len(re.findall(r"\S[ \u00a0\u202f][;!?]", text))
    tight = len(re.findall(r"[^\W_][;!?]", text))
    return spaced > tight


def _cp(spec):
    """'U+200B' -> '\\u200b';  'U+E0000-U+E007F' -> (start, end)."""
    if "-" in spec:
        a, b = spec.split("-")
        return (int(a[2:], 16), int(b[2:], 16))
    return int(spec[2:], 16)


def protect_urls(text):
    """Swap URLs for placeholders so no pass rewrites inside a link."""
    found = []

    def stash(m):
        found.append(m.group(0))
        return f"\x00URL{len(found) - 1}\x00"

    return URL_RE.sub(stash, text), found


def restore_urls(text, found):
    for i, url in enumerate(found):
        text = text.replace(f"\x00URL{i}\x00", url)
    return text


def pass_invisible(text, lex):
    """Delete or space-normalise invisible characters. Returns (text, hits)."""
    hits = []
    for entry in lex["invisible"]:
        cp = _cp(entry["cp"])
        if isinstance(cp, tuple):
            pattern = "[" + re.escape(chr(cp[0])) + "-" + re.escape(chr(cp[1])) + "]"
        else:
            pattern = re.escape(chr(cp))
        n = len(re.findall(pattern, text))
        if n:
            hits.append({"name": entry["cp"] + " " + entry["name"], "count": n,
                         "action": entry["action"]})
            text = re.sub(pattern, "" if entry["action"] == "delete" else " ", text)
    # Any remaining Cf (format) character is invisible by definition.
    stray = [c for c in text if unicodedata.category(c) == "Cf"]
    if stray:
        hits.append({"name": "other invisible format chars", "count": len(stray),
                     "action": "delete"})
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return text, hits


def pass_typographic(text, lex, lang="en", spaced=False):
    hits = []
    for entry in lex["typographic"]:
        ch = entry["from"]
        if lang == "fr" and ch == "·":
            # Inclusive writing (étudiant·e·s) is a choice, not an artefact.
            # Only a middle dot used as a bullet or separator is converted.
            n = len(re.findall(r"(?<![^\W\d_])·|·(?![^\W\d_])", text))
            if n:
                hits.append({"name": f"{ch} {entry['name']}", "count": n, "to": entry["to"]})
                text = re.sub(r"(?<![^\W\d_])·|·(?![^\W\d_])", entry["to"], text)
            continue
        n = text.count(ch)
        if not n:
            continue
        hits.append({"name": f"{ch} {entry['name']}", "count": n, "to": entry["to"].strip() or "(space)"})
        if ch == "—":
            # " word — word " and "word—word" both collapse to a comma + space.
            text = re.sub(r"\s*—\s*", ", ", text)
        elif ch == "–":
            text = re.sub(r"\s*–\s*(?=\d)", "-", text)      # 5–10  -> 5-10
            text = re.sub(r"\s+–\s+", ", ", text)            # used as em dash
            text = text.replace("–", "-")
        else:
            text = text.replace(ch, entry["to"])
    # A comma inserted before existing punctuation reads wrong.
    if lang == "fr":
        text = re.sub(r",\s*([,.])", r"\1", text)
        text = re.sub(r",[ \t]*([;:!?])", (" " if spaced else "") + r"\1", text)
    else:
        text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*\n", "\n", text)
    return text, hits


def _match_case(src, repl):
    if not repl:
        return repl
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


ELIDE = {"de": "d'", "que": "qu'", "ne": "n'", "se": "s'", "me": "m'", "te": "t'",
         "le": "l'", "la": "l'", "je": "j'"}
UNELIDE = {"d": "de", "qu": "que", "n": "ne", "s": "se", "c": "ce", "m": "me",
           "t": "te", "j": "je", "l": "le"}


def repair_elision(text):
    """French elides before a vowel. A swap can change what comes next.

    Each replacement was marked with \\x01. "de booster" became
    "de \\x01augmenter" and has to be "d'augmenter"; "d'\\x01" followed by a
    consonant goes the other way. Only marked spots are touched, so the
    writer's own text is never re-elided.
    """
    def keep_case(src, out):
        return out[0].upper() + out[1:] if src[0].isupper() else out

    text = re.sub(r"\b(de|que|ne|se|me|te|le|la|je)\s+\x01\s*(?=[" + FR_VOWELS + "])",
                  lambda m: keep_case(m.group(1), ELIDE[m.group(1).lower()]), text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\b(qu|d|n|s|c|m|t|j|l)['’]\x01\s*(?=[^\W\d_])(?![" + FR_VOWELS + "h])",
                  lambda m: keep_case(m.group(1), UNELIDE[m.group(1).lower()]) + " ", text,
                  flags=re.IGNORECASE)
    return text.replace("\x01", "")


def pass_lexical(text, lex, lang="en", spaced=False):
    """Replace slop words and phrases. Longest first so phrases win."""
    hits = []
    entries = sorted(lex["phrases"] + lex["words"],
                     key=lambda e: len(e["find"]), reverse=True)
    mark = "\x01" if lang == "fr" else ""
    for entry in entries:
        find = entry["find"]
        pattern = term_re(find, lang)
        found = pattern.findall(text)
        if not found:
            continue
        hits.append({"find": find, "replace": entry["replace"] or "(deleted)",
                     "count": len(found), "family": entry["family"]})
        text = pattern.sub(lambda m: mark + _match_case(m.group(0), entry["replace"]), text)
    if lang == "fr":
        text = repair_elision(text)
    # Clean up after deletions. Deleting a whole clause leaves orphaned
    # punctuation behind ("system. ." or a line that now opens on a comma),
    # and that reads worse than the slop did.
    text = re.sub(r"[ \t]{2,}", " ", text)
    lead = "[,.;:!?]" if lang == "fr" else "[,.;:]"
    text = re.sub(r"(?m)^[ \t]*(?:" + lead + r"+[ \t]*)+", "", text)
    text = re.sub(r"(?m)^[ \t](?=\S)", "", text)       # one space left by a deletion.
                                                      # Deeper indents are deliberate.
    if lang == "fr":
        # French puts a space before ; : ! ? in France and often not in
        # Quebec. Whichever this writer does, keep doing it.
        text = re.sub(r"\s+([,.])", r"\1", text)
        if not spaced:
            text = re.sub(r"\s+([;!?])", r"\1", text)
        text = re.sub(r",\s*([,.])", r"\1", text)
        text = re.sub(r",[ \t]*([;:!?])", (" " if spaced else "") + r"\1", text)
        text = re.sub(r"([;:])[ \t]*,", r"\1", text)   # "simple : en effet, c'est"
    else:
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r",\s*([,.;:!?])", r"\1", text)  # an em dash became a comma,
                                                      # then the clause after it went
    text = text.replace("...", "\x00ELL\x00")          # protect real ellipses
    text = re.sub(r"\.\s*\.+", ".", text)
    text = re.sub(r"([!?])\s*\.", r"\1", text)
    if lang == "fr":
        text = re.sub(r"\.[ \t]*[!?]+", ".", text)   # the "!" belonged to a deleted closer
    text = text.replace("\x00ELL\x00", "...")
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # An em dash that became a comma, followed by a sentence connective, leaves
    # a splice ("is important, also, it's proof"). Promote it to a full stop.
    connectives = FR_CONNECTIVES if lang == "fr" else r"also|so|still|basically|in the end"
    text = re.sub(r",\s*(" + connectives + r")\s*,\s*",
                  lambda m: ". " + m.group(1)[0].upper() + m.group(1)[1:] + ", ", text)
    return text, hits


def tu_vous_mix(text):
    """Counts of tu-forms and vous-forms. Both at once is a French tell."""
    tu = len(re.findall(r"(?i)\b(?:tu|toi|ton|ta|tes)\b|\bt['’](?=[" + FR_VOWELS + "])", text))
    vous = len(re.findall(r"(?i)\b(?:vous|votre|vos)\b", text))
    return tu, vous


def scan_structures(text, lex, lang="en"):
    flags = []
    for s in lex["structures"]:
        try:
            pattern = re.compile(s["regex"], re.MULTILINE)
        except re.error:
            continue
        found = pattern.findall(text)
        if found:
            flags.append({"name": s["name"], "count": len(found), "fix": s["fix"]})
    # Sentence-length uniformity is structural too.
    lens = [len(s.split()) for s in SENT_RE.findall(text) if len(s.split()) > 2]
    if len(lens) >= 4:
        mean = sum(lens) / len(lens)
        var = sum((n - mean) ** 2 for n in lens) / len(lens)
        cv = (var ** 0.5) / mean if mean else 0
        if cv < 0.35:
            flags.append({
                "name": f"Uniform sentence length (variation {cv:.2f})",
                "count": len(lens),
                "fix": "Break one sentence in half. Let another run long. Machines write even.",
            })
    if lang == "fr":
        tu, vous = tu_vous_mix(text)
        if tu and vous:
            flags.append({
                "name": f"Tu and vous mixed ({tu} tu, {vous} vous)",
                "count": tu + vous,
                "fix": "Pick one register and hold it. On Instagram that is usually tu. "
                       "Vous for a group is fine; vous for the reader who was tu a line ago is not.",
            })
    return flags


def restore_capitals(original, text, lang="en"):
    """Deleting an opener leaves the next word lower case.

    Only fix it for writers who capitalise their sentences in the first place:
    a deliberately lower-case voice is a style, not an artefact, and shouting
    over it would be exactly the kind of thing this script exists to stop.
    """
    letter, lower = ("[A-Za-z]", "[a-z]") if lang == "en" else (r"[^\W\d_]", r"[^\W\d_A-ZÀ-Þ]")
    starts = re.findall(r"(?:^|[.!?]\s+|\n)\s*(" + letter + ")", original)
    if not starts or sum(1 for c in starts if c.isupper()) * 2 < len(starts):
        return text
    return re.sub(r"(?:^|(?<=[.!?] )|(?<=[.!?]\n)|(?<=\n))\s*(" + lower + ")",
                  lambda m: m.group(0)[:-1] + m.group(1).upper(), text)


def humanize(text, lex, lang="en"):
    raw_for_case = text
    lex = lexicon_for(lex, lang)
    spaced = lang == "fr" and spaced_punctuation(text)
    text, urls = protect_urls(text)
    text, inv = pass_invisible(text, lex)
    text, typo = pass_typographic(text, lex, lang, spaced)
    text, lexi = pass_lexical(text, lex, lang, spaced)
    text = restore_capitals(raw_for_case, text, lang)
    text = restore_urls(text, urls)
    return text.strip() + "\n", {
        "invisible": inv,
        "typographic": typo,
        "lexical": lexi,
        "structures": scan_structures(text, lex, lang),
    }


def render_report(report, out=sys.stderr, lang="en"):
    def head(title):
        print(f"\n{title}\n" + "-" * len(title), file=out)

    total = sum(h["count"] for h in report["invisible"]) \
        + sum(h["count"] for h in report["typographic"]) \
        + sum(h["count"] for h in report["lexical"])

    head("HUMANIZE REPORT" + ("  ·  français" if lang == "fr" else ""))
    print(f"{total} machine artefacts removed, "
          f"{len(report['structures'])} structural tells flagged for rewrite", file=out)

    if report["invisible"]:
        head("1. INVISIBLE CHARACTERS")
        for h in report["invisible"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['action']}", file=out)
    if report["typographic"]:
        head("2. TYPOGRAPHY")
        for h in report["typographic"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['to']}", file=out)
    if report["lexical"]:
        head("3. SLOP LEXICON")
        for h in report["lexical"]:
            print(f"  {h['count']:>3}x  {h['find']}  -> {h['replace']}   [{h['family']}]", file=out)
    if report["structures"]:
        head("4. STRUCTURAL TELLS  (not auto-fixed - rewrite these yourself)")
        for h in report["structures"]:
            print(f"  {h['count']:>3}x  {h['name']}\n        {h['fix']}", file=out)
    if not any(report.values()):
        head("CLEAN")
        print("  Nothing to strip.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Strip the machine fingerprint out of a draft.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("-o", "--out", help="write cleaned text here instead of stdout")
    ap.add_argument("--report", action="store_true", help="print what changed, to stderr")
    ap.add_argument("--json", action="store_true", help="emit {text, report} as JSON")
    ap.add_argument("--lexicon", default=LEX, help="path to slop.json")
    ap.add_argument("--lang", choices=["auto", "en", "fr"],
                    help="language of the draft (default: IG_LANG, else read from the text)")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    lex = load_lexicon(args.lexicon)
    lang = resolve_lang(args.lang, raw)
    clean, report = humanize(raw, lex, lang)

    if args.json:
        payload = {"text": clean, "report": report}
        if lang != "en":
            payload["lang"] = lang
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(clean)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(clean)
    if args.report:
        render_report(report, lang=lang)


if __name__ == "__main__":
    main()

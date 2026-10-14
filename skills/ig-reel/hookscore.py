#!/usr/bin/env python3
"""
hookscore.py - score the first line of a Reel on the five things strong hooks
have in common, and rank a batch of them against each other.

What this is:  five local heuristics, computed on your machine from the text
alone. They measure properties that hooks which hold attention tend to share -
a length you can say in under three seconds, a concrete marker, something at stake,
the payload at the front rather than the back, and a viewer to aim it at.

What this is NOT:  a view predictor. It was tested against 74 real short-form
hooks, transcribed from the first three seconds of the top eight and bottom
eight performers on five channels. Separating a real hook from a deliberately
bad one it does well: AUC 0.83, and 9 of 10 written-to-be-bad hooks scored
below the real median. Separating a good creator's hits from that same
creator's misses it barely does at all: AUC 0.56, where 0.50 is a coin flip.

So use it for what it measured well. It catches greetings, preambles, hooks
with nothing concrete in them and hooks that take five seconds to say. It will
not tell you which of two decent hooks will travel, and nothing that reads text
can, because that is decided by your face, your edit, your audio and who
Instagram shows it to. Trust the retention graph over this script.

Each check returns 0 to 100. Higher is better.

English and French. --lang auto (the default) reads the hooks and picks. The
French panel uses French stakes, spoken numbers ("vingt mille euros"), weak
openers ("alors", "salut", "dans cette vidéo"), tu and vous for ADDRESS, and a
slightly longer word budget, because French needs about 15% more words than
English to say the same thing in the same time. The thresholds were not
re-measured on a French corpus; the English numbers above are the evidence.

Usage
  python3 hookscore.py hooks.txt              # one hook per line, ranked
  python3 hookscore.py --hook "I lost $18,000 on one missing contract."
  pbpaste | python3 hookscore.py -
  python3 hookscore.py hooks.txt --json
  python3 hookscore.py accroches.txt --lang fr
"""

import argparse
import json
import os
import re
import statistics
import sys

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
NUMBER_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"                       # money, whole
    r"|\b\d[\d,]*(?:\.\d+)?\s?"                      # a figure, with or
    r"(?:%|k\b|x\b|hrs?\b|hours?\b|mins?\b|minutes?\b"  # without a unit
    r"|days?\b|weeks?\b|months?\b|years?\b)?",
    re.IGNORECASE)
PROPER_RE = re.compile(r"(?<!^)\b[A-Z][a-z]{2,}\b")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

# Spoken hooks say their numbers out loud. "Zero dollars" and "twenty grand"
# are as concrete as "$0" and "$20,000", and counting only digits missed them.
# "one" and "first" are deliberately absent: they are filler far more often
# than they are a quantity.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
}

# Words that put something on the line. A hook with none of these is a
# statement; a hook with one is a reason to keep watching.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first",
    "banned", "illegal", "worst", "hate", "hated", "wasted", "waste", "scam",
    "lie", "lied", "lying", "truth", "secret", "hidden", "stole", "stolen",
    "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
}

# Openers that spend the first second saying nothing.
WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
]

# Imperatives that earn the front position.
IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
}

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll)"),
     "Opens with \"stop scrolling\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how)\b"),
     "Video preamble. Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome )"),
     "Greeting. Nobody came to the feed to be greeted."),
    (HASHTAG_RE,
     "Hashtag in the hook. Hashtags belong at the bottom of the caption, if anywhere."),
    (EMOJI_RE,
     "Emoji in the hook. On-screen text at hook size has room for words or for an emoji, not both."),
]


# French. Same five properties, French evidence. Tokens are compared with
# their elision taken off, so "n'arrête" counts as "arrête" and "l'erreur" as
# "erreur"; openers are compared as written, because "c'est" is the opener.
WORD_RE_FR = re.compile(r"[\w$%€'’-]+(?:,\d+)?")
NUMBER_RE_FR = re.compile(
    r"[$€]\s?\d[\d.]*(?:,\d+)?"
    r"|\b\d[\d.]*(?:,\d+)?\s?"
    r"(?:%|€|\$|k\b|x\b|h\b|heures?\b|min\b|minutes?\b"
    r"|jours?\b|semaines?\b|mois\b|ans\b|années?\b)?",
    re.IGNORECASE)
PROPER_RE_FR = re.compile(r"(?<!^)\b[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]{2,}\b")
THOUSANDS_FR = re.compile(r"(?<=\d)[ \u00a0\u202f.](?=\d{3}(?!\d))")
ELISION_FR = re.compile(r"^(?:[ldjmntsc]|qu|lorsqu|puisqu|jusqu)['’]")

SPOKEN_NUMBERS_FR = {
    "zéro", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "quinze", "vingt", "trente", "quarante",
    "cinquante", "soixante", "cent", "cents", "mille", "million", "millions",
    "milliard", "milliards", "douzaine", "moitié", "double", "triple",
}
MONEY_WORDS_FR = {
    "euros", "euro", "balles", "dollars", "dollar", "centimes", "pourcent",
    "salaire", "loyer", "bénéfice", "bénéfices", "revenus", "millionnaire",
    "milliardaire", "smic", "facture", "k€",
}
STAKES_FR = {
    "arrête", "arrêtez", "stop", "jamais", "faux", "fausse", "erreur", "erreurs",
    "perdu", "perdue", "perdre", "perds", "perte", "coûté", "coûte", "coûtent",
    "ruiné", "fauché", "raté", "échoué", "échec", "personne", "pas", "rien",
    "viré", "virée", "supprimé", "supprime", "tué", "tue", "remplacé", "remplace",
    "battu", "gratuit", "gratuite", "payé", "facturé", "embauché", "économisé",
    "premier", "première", "interdit", "illégal", "pire", "déteste", "détesté",
    "gaspillé", "arnaque", "mensonge", "menti", "vérité", "secret", "secrets",
    "caché", "cachée", "volé", "avant", "sauf", "problème", "risque", "danger",
    "attention", "regret", "regrette", "aurais", "devrais", "encore", "déjà",
    "seulement", "sans", "contre", "vs", "vraiment", "mais", "plutôt", "quitté",
    "abandonné", "faillite",
}
WEAK_OPENERS_FR = [
    "alors", "donc", "ok", "okay", "bon", "bah", "ben", "salut", "coucou",
    "hello", "hey", "yo", "bonjour", "bonsoir", "bienvenue", "aujourd'hui",
    "en gros", "honnêtement", "franchement", "écoute", "écoutez", "euh",
    "juste", "je voulais", "je veux", "je vais", "un des", "une des",
    "l'un des", "est-ce que", "est-ce", "tu as", "vous avez", "as-tu",
    "avez-vous", "dans cette", "dans ce", "dans la", "le truc", "il y a",
    "y'a", "c'est", "voici", "voilà", "quand on", "tu sais", "vous savez",
    "en tant que", "laisse-moi", "laissez-moi",
]
IMPERATIVES_FR = {
    "arrête", "arrêtez", "vole", "volez", "pique", "piquez", "copie", "copiez",
    "supprime", "supprimez", "essaie", "essaye", "essayez", "regarde",
    "regardez", "lis", "lisez", "enregistre", "enregistrez", "utilise",
    "utilisez", "construis", "fais", "faites", "écris", "écrivez", "envoie",
    "envoyez", "prends", "prenez", "commence", "commencez", "quitte", "jamais",
    "toujours", "mets", "mettez", "lance", "lancez", "vérifie", "vérifiez",
    "ne", "oublie", "oubliez", "évite", "évitez", "garde", "gardez", "teste",
    "testez",
}
YOU_RE_FR = re.compile(r"\b(?:tu|te|toi|ton|ta|tes|vous|votre|vos)\b|\bt['’]", re.IGNORECASE)
ME_RE_FR = re.compile(r"\b(?:je|me|moi|mon|ma|mes|nous|notre|nos|on)\b|\b[jm]['’]", re.IGNORECASE)
HASHTAG_RE_FR = re.compile(r"(?:^|\s)#\w+")

DEALBREAKERS_FR = [
    (re.compile(r"(?i)^\s*(?:arrête(?:z)? de (?:scroller|défiler)|ne (?:scrolle|scrollez|défile|défilez) pas"
                r"|stop(?:pe)? (?:au |le )?scroll)"),
     "Opens with \"arrête de scroller\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:dans (?:cette|la) vidéo|dans ce reel|dans la vidéo d['’]aujourd['’]hui"
                r"|je vais (?:te|vous) (?:montrer|expliquer|apprendre))\b"),
     "Video preamble. Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:salut|coucou|bonjour|bonsoir|hello|hey|yo|bienvenue|ça va)\b"),
     "Greeting. Nobody came to the feed to be greeted."),
    (HASHTAG_RE_FR,
     "Hashtag in the hook. Hashtags belong at the bottom of the caption, if anywhere."),
    (EMOJI_RE,
     "Emoji in the hook. On-screen text at hook size has room for words or for an emoji, not both."),
]

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


def clamp(n):
    return max(0.0, min(100.0, n))


def words(text, lang="en"):
    # "$18,000" is one word when it is spoken, so it is one word here too.
    if lang == "fr":
        return WORD_RE_FR.findall(THOUSANDS_FR.sub("", text))
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def norm_fr(token):
    return ELISION_FR.sub("", token.lower().replace("’", "'")).strip("'")


def check_length(text, lang="en"):
    """A hook has to land before the thumb moves. Roughly two seconds."""
    w = words(text, lang)
    n = len(w)
    # French says the same thing in more, shorter words, and says them faster.
    most, wps, max_chars = (14, 2.9, 70) if lang == "fr" else (12, 2.75, 60)
    secs = n / wps                       # ~165 words per minute spoken, ~175 in French
    chars = len(text.strip())
    if 5 <= n <= most:
        score = 100.0
    elif n < 5:
        score = clamp(100 - (5 - n) * 20)
    else:
        score = clamp(100 - (n - most) * 11)
    if chars > max_chars:                # two lines of big on-screen text
        score -= 12
    return clamp(score), f"{n} words, {chars} chars, ~{secs:.1f}s spoken (want 5-{most} words)"


def check_specificity(text, lang="en"):
    """One concrete thing beats three abstract ones."""
    if lang == "fr":
        flat = THOUSANDS_FR.sub("", text)
        nums = [n.strip() for n in NUMBER_RE_FR.findall(flat) if n.strip()]
        propers = set(PROPER_RE_FR.findall(flat))
        low = [norm_fr(w) for w in words(text, lang)]
        spoken = [w for w in low if w in SPOKEN_NUMBERS_FR or w in MONEY_WORDS_FR]
    else:
        nums = [n.strip() for n in NUMBER_RE.findall(text) if n.strip()]
        propers = set(PROPER_RE.findall(text))
        low = [w.lower().strip("'’") for w in words(text)]
        spoken = [w for w in low if w in SPOKEN_NUMBERS or w in MONEY_WORDS]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    return score, (f"{hits} concrete marker(s)" + (f": {found}" if found else
                   " - no number, no name, nothing checkable"))


def check_stakes(text, lang="en"):
    """Tension, cost, negation. Something the viewer might lose."""
    if lang == "fr":
        hits = [x for x in (norm_fr(t) for t in words(text, lang)) if x in STAKES_FR]
        priced = re.search(r"[$€]\s?\d|\d\s?(?:€|\$|euros?\b)", text)
    else:
        w = [x.lower().strip("'’") for x in words(text)]
        hits = [x for x in w if x in STAKES]
        priced = re.search(r"\$\s?\d", text)
    markers = sorted(set(hits))
    if priced:
        markers.append("a price")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"{n} tension marker(s)" + (f": {', '.join(markers[:4])}" if markers else
                                         " - nothing is at stake in this line")
    return clamp(score), detail


def check_frontload(text, lang="en"):
    """The interesting word cannot be in position nine."""
    w = words(text, lang)
    if not w:
        return 0.0, "empty"
    penalty = 0
    hit_opener = None
    payload = None
    if lang == "fr":
        raw = [x.lower().replace("’", "'") for x in w]
        opener = " ".join(raw[:2]) + " "
        for weak in WEAK_OPENERS_FR:
            if opener.startswith(weak + " "):     # whole words: "bon" is not "bonne"
                penalty, hit_opener = 30, weak
                break
        for i, token in enumerate(norm_fr(x) for x in w):
            if (token in STAKES_FR or token in SPOKEN_NUMBERS_FR or token in MONEY_WORDS_FR
                    or NUMBER_RE_FR.match(w[i]) or (i and PROPER_RE_FR.match(w[i]))):
                payload = i
                break
    else:
        low = [x.lower().strip("'’") for x in w]
        opener = " ".join(low[:2])
        for weak in WEAK_OPENERS:
            if opener.startswith(weak) or low[0] == weak:
                penalty, hit_opener = 30, weak
                break
        for i, token in enumerate(low):
            if (token in STAKES or token in SPOKEN_NUMBERS or token in MONEY_WORDS
                    or NUMBER_RE.match(w[i]) or (i and PROPER_RE.match(w[i]))):
                payload = i
                break
    if payload is None:
        base = 30.0
        where = "no payload word anywhere in the line"
    elif payload <= 3:
        base = 100.0
        where = f"payload at word {payload + 1}"
    elif payload <= 6:
        base = 70.0
        where = f"payload at word {payload + 1}, could move forward"
    else:
        base = 40.0
        where = f"payload at word {payload + 1}, too late"
    detail = where + (f"; weak opener \"{hit_opener}\"" if hit_opener else "")
    return clamp(base - penalty), detail


def check_address(text, lang="en"):
    """Aimed at one viewer, or floating in the air."""
    if lang == "fr":
        first = norm_fr(words(text, lang)[0]) if words(text, lang) else ""
        if YOU_RE_FR.search(text):
            return 100.0, "speaks to the viewer"
        if first in IMPERATIVES_FR:
            return 90.0, f"imperative opener (\"{first}\")"
        if ME_RE_FR.search(text):
            return 70.0, "first person, no viewer named"
        return 35.0, "third person, nobody in the room"
    low = text.lower()
    w = [x.lower().strip("'’") for x in words(text)]
    if re.search(r"\b(you|your|you're|youre|yourself)\b", low):
        return 100.0, "speaks to the viewer"
    if w and w[0] in IMPERATIVES:
        return 90.0, f"imperative opener (\"{w[0]}\")"
    if re.search(r"\b(i|my|me|we|our)\b", low):
        return 70.0, "first person, no viewer named"
    return 35.0, "third person, nobody in the room"


CHECKS = ["LENGTH", "SPECIFICITY", "STAKES", "FRONTLOAD", "ADDRESS"]


def run(text, lang="en"):
    results = {
        "LENGTH": check_length(text, lang),
        "SPECIFICITY": check_specificity(text, lang),
        "STAKES": check_stakes(text, lang),
        "FRONTLOAD": check_frontload(text, lang),
        "ADDRESS": check_address(text, lang),
    }
    dealbreakers = DEALBREAKERS_FR if lang == "fr" else DEALBREAKERS
    flags = [msg for pattern, msg in dealbreakers if pattern.search(text)]
    scores = [results[c][0] for c in CHECKS]
    # The weakest property caps the hook, same logic as detect.py: one bad
    # property is enough for the thumb to keep moving.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15
    overall = clamp(overall)
    verdict = "STRONG" if overall >= 70 and min(scores) >= 55 and not flags else (
        "OK" if overall >= 50 else "WEAK")
    return results, overall, verdict, flags


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render_one(text, results, overall, verdict, flags, out=sys.stdout, lang="en"):
    print("\nHOOK SCORE" + ("  ·  français" if lang == "fr" else ""), file=out)
    print("=" * 62, file=out)
    print(f"  \"{text.strip()}\"\n", file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HOOK SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    for f in flags:
        print(f"\n  DEALBREAKER  {f}", file=out)
    if verdict != "STRONG":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest property: {weakest}. Fix that one and re-run.", file=out)
    print("", file=out)


def render_table(rows, out=sys.stdout, lang="en"):
    print("\nHOOK RANKING" + ("  ·  français" if lang == "fr" else "") + "\n" + "=" * 78, file=out)
    for i, r in enumerate(rows, 1):
        mark = "->" if i == 1 else "  "
        hook = r["hook"] if len(r["hook"]) <= 62 else r["hook"][:59] + "..."
        print(f"{mark} {r['score']:5.1f} {r['verdict']:<7} {hook}", file=out)
        print(f"        weakest: {r['weakest']} ({r['checks'][r['weakest']]['score']:.0f})", file=out)
        for f in r["flags"]:
            print(f"        dealbreaker: {f}", file=out)
    print("\nShoot the top one. If the top one is under 50, none of these are the hook.\n",
          file=out)


def main():
    ap = argparse.ArgumentParser(description="Score a Reel hook on five properties.")
    ap.add_argument("input", nargs="?", default="-", help="file with one hook per line, or -")
    ap.add_argument("--hook", help="score a single hook given on the command line")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", choices=["auto", "en", "fr"],
                    help="language of the hooks (default: IG_LANG, else read from all of them together)")
    args = ap.parse_args()

    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        print("nothing to score", file=sys.stderr)
        sys.exit(2)

    # One language for the batch, read from all the hooks together: a single
    # short hook is a thin sample and every row should be ranked on one ruler.
    lang = resolve_lang(args.lang, "\n".join(lines))
    payload = []
    for line in lines:
        results, overall, verdict, flags = run(line, lang)
        payload.append({
            "hook": line,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "weakest": min(CHECKS, key=lambda c: results[c][0]),
            "flags": flags,
            "score": round(overall, 1),
            "verdict": verdict,
            **({"lang": lang} if lang != "en" else {}),
        })

    if args.json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return

    if len(payload) == 1:
        results, overall, verdict, flags = run(lines[0], lang)
        render_one(lines[0], results, overall, verdict, flags, lang=lang)
    else:
        render_table(sorted(payload, key=lambda r: -r["score"]), lang=lang)

    sys.exit(0 if max(p["score"] for p in payload) >= 70 else 1)


if __name__ == "__main__":
    main()

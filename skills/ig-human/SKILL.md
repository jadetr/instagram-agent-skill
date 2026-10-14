---
name: ig-human
description: >-
  Strip the machine fingerprint out of any draft - em dashes, AI slop words,
  invisible watermark characters - and score it against a five-check detection
  panel before it goes out. Use whenever text needs to sound human, when the
  user says humanize, "does this sound like AI", "remove the em dashes",
  "de-slop this", "this sounds like ChatGPT", or before any caption, script,
  comment, reply or DM is shown to the user.
  Also in French: "humanise ce texte", "ça sonne IA", "enlève les tirets",
  "ça fait ChatGPT".
---

# ig-human

Two tools live in this folder and they both actually run. Use them. Do not
eyeball this.

```bash
python3 humanize.py draft.txt --report        # clean it, show what changed
python3 detect.py draft.txt                    # score it, five checks
python3 detect.py before.txt after.txt         # prove the delta
```

Both read `slop.json`: 154 stock words and phrases with plain-English
replacements, 18 invisible character classes, 11 typographic substitutions and
16 structural tells. The last block of each list is Instagram-specific, the
vocabulary that only shows up in captions and voiceovers. It is meant to be
edited. If the user has a word they always use that the lexicon strips, take it
out of the file.

## Why this matters more on Instagram than it looks

Captions are short and scripts get said out loud. A written-sounding line in a
600-character caption is a larger share of the text than the same line in an
essay, and a voiceover that nobody could say naturally is obvious in the first
take. The tell here is not a detector flagging the post. The tell is a person
scrolling past something that reads like a brand, or a creator stumbling over
their own script.

## What gets fixed automatically

**1. Invisible characters.** Zero-width spaces and joiners, word joiners, soft
hyphens, byte-order marks, Unicode tag characters, invisible separators,
non-breaking and narrow spaces. A keyboard does not produce these. They survive
copy-paste, they are invisible in every editor, and they are the most
mechanical thing in generated text. `humanize.py` deletes every one, including
any remaining Unicode format character it does not have a name for.

**2. Typography.** Em dash to comma, en dash to hyphen, curly quotes to
straight, ellipsis to three dots, bullet character to hyphen. The em dash pass
is the one that matters: it collapses the dash to a comma and then cleans up
the double punctuation and orphaned periods that leaves behind.

**3. The slop lexicon.** delve, leverage, robust, seamless, crucial, testament
to, "in today's fast-paced world", plus the Instagram block: "stop scrolling",
"in today's video", "follow for more", "tag someone who needs this", "the
algorithm loves", "run don't walk". Each swapped for a plain word or deleted,
with capitalisation preserved and URLs left untouched.

## What does NOT get fixed automatically

Structural tells get **flagged, not rewritten**, because changing the shape of
a sentence needs judgement:

- "It's not just X, it's Y" and "not only X but also Y"
- Rule-of-three triads
- Rhetorical one-word question lines: "The result?"
- The video preamble: "in this video I'm going to show you"
- Emoji bullet lists
- Three or more shouted words in a row
- Hashtag walls
- Reflex bait: "follow for more", "tag someone who", "double tap if"

That list is your job. Rewrite each flagged line by hand, keeping the meaning,
then re-run `detect.py`. This is the part that moves the score from REVIEW to
PASS, and it is the part a script cannot do.

## In French

Both scripts read French. `--lang auto` is the default, `--lang fr` forces it.
The French lexicon is the `fr` block of `slop.json`: about 250 terms written
for French as it is actually generated (plonger dans, tirer parti de, booster,
crucial, incontournable, véritable, en effet, il est important de noter que,
n'hésitez pas, arrête de scroller, dans cette vidéo je vais te montrer,
abonne-toi pour plus) and 17 structural tells, including "Ce n'est pas juste X,
c'est Y" and "Non seulement... mais aussi".

What is different in French:

- **Elision is repaired.** "de booster" becomes "d'augmenter", not "de
  augmenter". Inflected forms are listed one by one, so a swap keeps gender and
  number.
- **The writer's punctuation habit is kept.** A space before `? !` (France) or
  none (Quebec, most phones): whichever the draft does, the output does.
- **Inclusive writing is left alone.** A middle dot inside a word is not a
  bullet.
- **Mixing tu and vous is flagged.** It is the most common error in generated
  French.
- **`detect.py` reads spoken French** ("ça", "c'est pas", "t'as") where it
  reads contractions in English, and a fine space before `;:!?` is correct
  French typography, not a fingerprint.

The rest of what makes French copy sound generated (calques, Title Case,
English typography, the wrong register) is not something a regex can fix
safely. It is in `french.md`, in this folder. Read it, then rewrite by hand
like any structural tell.

## The five checks

`detect.py` scores five signals 0-100, higher is more human:

| check | what it measures | machine looks like |
| --- | --- | --- |
| BURSTINESS | sentence-length variation | every sentence the same length |
| SPECIFICITY | numbers, names, concrete markers per 100 words | abstract nouns, no figures |
| SLOP DENSITY | lexicon hits per 100 words | stock vocabulary |
| FINGERPRINT | invisible chars, em dashes, curly quotes per 1k chars | typographically perfect |
| VOICE | contractions, person, structural tells | no contractions, staged reveals |

The verdict weights the mean at 60% and the **weakest single check** at 40%,
because one signal is enough. PASS needs an overall of 70+ with no check
below 55.

## Say this honestly

These are five local heuristics modelled on the signals public detectors key
on. They run entirely on the user's machine and nothing is uploaded. They are
**not** GPTZero, Originality, Copyleaks, Winston or Turnitin, they do not call
those APIs, and they cannot promise those verdicts. Fixing what they measure
does tend to move those numbers, because they are measuring the same underlying
things. That is the claim. Do not make a bigger one on the user's behalf, and
do not tell a user their text is undetectable.

## Order of operations

1. `humanize.py draft.txt -o clean.txt --report`
2. Read the structural flags. Rewrite those lines yourself.
3. `detect.py draft.txt clean.txt` to show the before and after.
4. If the verdict is not PASS, fix the weakest check named in the output and go
   again. Two rounds is normal. Five means the draft was written by formula,
   and the fix is a different draft, not more passes.
5. Show the user the cleaned text and the score. Never the score alone.

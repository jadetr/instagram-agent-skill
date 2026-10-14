# Writing in French

Every skill in this pack writes in English or French. This file is what changes
when it is French. Read it before drafting anything in French, and read it
again before the humanizer pass, because most of what makes French copy sound
generated is in here and not in the lexicon.

## Which language

In this order:

1. `~/.claude/instagram/voice.md`, the **Language** section. The language the
   user posts in, and which French.
2. The language of the user's own samples: the reels, captions or comments
   they pasted.
3. The language they are talking to you in.

The post and the conversation can differ. A Montreal creator can chat with you
in French and post in English. voice.md wins. If it does not say and the
samples are mixed, ask once: "French, English, or both?"

**One language per post.** A bilingual caption doubles the length and pushes
the second language below the "... more", where nobody reads it. If the
account serves both, write two posts or pick the language of the audience this
post is for.

## Write it in French, do not translate it

A translated script sounds like a dubbed film, and people hear it in the first
line. Start from the idea and write the French the user would say.

Signs that a line was translated:

- **Calques.** "À la fin de la journée" (at the end of the day), "faire du
  sens" outside Quebec, "adresser un problème" (address), "c'est un
  no-brainer", "être excité" (excited, which is not what it means), "supporter
  quelqu'un" for soutenir in France.
- **English rhythm.** Three short punchy fragments in a row. French carries a
  thought further in one sentence and then cuts hard.
- **Title Case.** "Les 5 Erreurs À Éviter" is English capitalisation. French
  titles take sentence case: "Les 5 erreurs à éviter".
- **English typography.** "$18,000", "2.5%", "Dec. 18" in a French caption.
- **"Vous" with a capital in the middle of a sentence.** That is a letter to a
  minister, not a caption.

## Tu or vous

**Tu, almost always, on Instagram.** Vous for a luxury brand, a legal or
medical practice, a B2B audience that expects it, or an older audience that
does. voice.md says which.

**Never both in the same post.** Mixing them is the most common error in
generated French, and `humanize.py` and `detect.py` flag it. Vous addressing a
group ("vous êtes nombreux à me demander") inside a tu post is fine. Vous for
the same reader who was tu one line earlier is not.

Comments, replies and DMs mirror the other person: if they wrote tu, reply tu.
If you cannot tell, tu for a creator and vous for a brand account, in France.
Quebec is more tu across the board.

## Which French

Ask, or read it from voice.md. It changes the words and the punctuation.

| | France | Quebec | Belgium / Switzerland |
| --- | --- | --- | --- |
| space before `? ! ;` | yes | usually no | yes |
| space before `:` | yes | yes | yes |
| money | 18 000 € | 18 000 $ | 18 000 € / 18 000 CHF |
| email | mail, e-mail | courriel | mail |
| weekend | week-end | fin de semaine | week-end |
| a DM | un DM, un MP | un DM, un message privé | un DM, un MP |
| 70, 90 | soixante-dix, quatre-vingt-dix | same | septante, nonante |

Never fake a variety the user does not speak. No "tsé", "pis" or "c'est
plate" for someone from Lyon, and no "grave" or "de ouf" for someone from
Quebec City, unless their own samples use them.

## Typography

- **Spaces before `? ! ; :`** follow the variety above. On a phone it is a
  normal space; the fine non-breaking space is a print habit, and `humanize.py`
  turns non-breaking spaces into normal ones. Whatever the user does, do the
  same thing every time. The humanizer keeps their habit rather than imposing
  one.
- **Numbers:** `18 000` with a space, `2,5 %` with a decimal comma, `€` after
  the number with a space, `14 h 30` or `14h30`, `le 18 décembre 2025`.
- **Quotes:** « » or " ", whichever the user uses. Both are fine on Instagram.
- **Accents on capitals.** "ÉTÉ", "À FAIRE", "ÇA". Dropping them in on-screen
  caps is a typo, not a style.
- **Inclusive writing** (créateur·ices, étudiant·e·s) only if the user does it.
  If they do, the humanizer leaves the middle dots alone.
- **Em dashes** are the same tell in French as in English. A comma, a colon or
  a full stop does the job.

## Spoken French, for anything said out loud

Reels, stories and voiceovers are spoken French, not written French:

- "On" for "nous". "Ça" for "cela".
- Drop the "ne" if the user does: "c'est pas", "j'sais pas". Most people do on
  camera, and a script with every "ne" in it sounds read.
- No passé simple, no imperfect subjunctive, no "afin de", "néanmoins", "en
  outre". Nobody says them to a camera.
- Short words. French has more syllables per idea than English, and
  `beats.py` times French at 175 words a minute.

## Length

French runs about 15% longer than English for the same idea. That costs the
most in the places that were already tight:

- **The first 125 characters of a caption** hold fewer words. The hook has to
  be shorter, not the fold longer.
- **On-screen text** stays at six words. Cut articles and auxiliaries before
  you cut the idea: "TES 30 PREMIERS VONT FLOPPER", not "TES TRENTE PREMIERS
  REELS VONT FAIRE UN FLOP".
- **Hooks**: `hookscore.py` allows 5 to 14 words in French against 5 to 12 in
  English.

## Instagram vocabulary

Use the words the user's audience uses. Most French-speaking creators say reel,
story, post, DM, feed, hook, carrousel, bio, abonnés, légende for the caption,
enregistrements for saves, partages for shares. Keep the anglicisms the user
says out loud, and do not add ones they do not.

## Keywords, hashtags, search

- **Keyword CTAs without accents.** "Commente CONTRAT", not "Commente RÉSUMÉ".
  People type on phones without accents, and an auto-reply matching "RÉSUMÉ"
  misses everyone who typed "RESUME". One word, capitals, no spaces.
- **Search terms in French**, written the way people type them into the search
  bar, in a normal sentence in the caption.
- **Hashtags in French** when the audience searches in French
  (#entrepreneuriat, #marketingdigital, #freelancequebec). Up to five. #pourtoi
  is the French #fyp and describes nothing.

## The scripts

Every script reads French. `--lang auto` is the default and decides from the
text; pass `--lang fr` to force it, or set `IG_LANG=fr` once for a user who
writes in French. What changes:

| script | in French |
| --- | --- |
| `humanize.py` | French lexicon, elision repaired after a swap, the user's spacing kept, inclusive dots kept, tu/vous mix flagged |
| `detect.py` | "ça", "c'est pas", "t'as" count as spoken voice; 18 000 € is one number; French typographic spaces are not a fingerprint |
| `caption.py` | French asks (commente, lien en bio, abonne-toi), accented hashtags, #pourtoi on the filler list |
| `hookscore.py` | French stakes, spoken numbers and weak openers, tu/vous for ADDRESS, 5 to 14 words |
| `beats.py` | 175 wpm, French function words ignored when checking the loop |
| `swipe.py` | French formula names and patterns per row, French column headers accepted |

The script reports stay in English. When you show the user a receipt, write it
in the language you are talking to them in.

The French thresholds use the English calibration (see the README). They were
not re-measured on a French corpus, so treat a French score as a sanity check,
the same way the English one is meant to be used.

# TTS wiring — the voice must speak the script's language

A talking avatar is only as good as its audio track. The single most
common agent mistake is synthesizing a German script with an English
voice (or a Persian script with an Arabic one): umlauts/ß mispronounce,
rhythm breaks, digits read wrong. **Never cross voices across
languages.**

## Per-language recommendations

### German (de)

- **Piper** (local, free, offline): `de_DE-thorsten-medium` — natural,
  fast. Best default for drafts and for anything that must run offline.
- **Edge-TTS** (free, needs network): `de-DE-KatjaNeural` /
  `de-DE-ConradNeural`. Slightly more natural than Piper.
- **ElevenLabs** (paid): when studio quality is needed; supports
  German well.
- Gotcha: German TTS must handle `ä ö ü ß` and compound-word stress.
  An English voice reads "für" as "furr". Always spot-check the WAV.

### Persian (fa)

- **Piper** (local, free): fa voices (e.g. `fa_IR` models) — check the
  specific model handles Persian digits and ZWNJ phrasing naturally.
- **Edge-TTS** (free, needs network): `fa-IR-DilaraNeural` /
  `fa-IR-FaridNeural`.
- Gotcha: mixed Persian/Latin text (URLs, brand names) — preview how
  the voice reads them; some voices spell out Latin words letter by
  letter.

### English (en)

- **Piper** (local, free) or **Edge-TTS** (`en-US-AriaNeural`,
  `en-GB-SoniaNeural`). Match the accent to the audience.

## Workflow

1. Synthesize the script to **WAV** (not MP3) when possible — WAV
   gives the preflight an exact duration.
2. Re-run the preflight on the WAV:
   `avatar_route.py --image face.png --audio voice.wav ...`
3. Keep clips ≤30s per segment on weak GPUs / for cheaper API billing;
   stitch segments after.
4. Target pace: ~140 wpm German, ~150 wpm English, ~130 wpm Persian —
   the tool's text-duration estimate uses these (labeled estimate).

## What this skill does not do

It does not synthesize audio itself — it routes you to the right TTS
and validates the result. Voice cloning (HeyGen/ElevenLabs) is a paid
feature of those platforms; the skill only notes where it lives.

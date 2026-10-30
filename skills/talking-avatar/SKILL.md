---
name: talking-avatar
description: Route a talking-avatar job to the right backend — free local SadTalker, rented-GPU SadTalker, Hedra API, or HeyGen API — from budget, quality target, GPU/VRAM and language, and preflight the portrait + audio before any render. Use when an agent must turn a portrait and a script or voice track into a talking-head video, when choosing between avatar backends, when a SadTalker render fails on a cartoon face or a weak GPU, or when wiring German/Persian TTS for the voice track. Never default to one vendor: route first, with the bundled tool.
---

# Talking-avatar router — pick the backend that fits, then prove the assets

Agents pick a talking-avatar backend by habit: one vendor's skill is
installed, so every portrait becomes that vendor's render. The habit
wastes money and time. A free local SadTalker run is right for a draft
on a good GPU; a HeyGen render is right for studio quality with budget;
a cartoon fox face fails on SadTalker no matter how good the GPU is;
a 2GB laptop GPU makes local SadTalker a bad afternoon. This skill is
the decision layer the single-vendor skills do not have: **preflight
the assets, route to the backend that fits, then render.**

## The contract

1. **Preflight first, with the tool — never send a bad asset to a
   render.** Run the bundled router (zero-dependency, Python stdlib
   only) on the final portrait and audio/script:

   ```bash
   python3 scripts/avatar_route.py --image face.png --audio voice.wav \
       --budget free --quality good --vram-gb 2 --gpu-vendor nvidia --lang de
   # or a JSON job file:
   python3 scripts/avatar_route.py --job job.json
   ```

   Exit codes: `0` = route decided · `1` = preflight errors, no route
   (fix the asset, do not render) · `2` = usage error.

   The preflight catches what wastes renders: missing/corrupt images,
   non-PNG/JPEG formats, sub-256px portraits, extreme aspect ratios,
   >10MB uploads, missing audio, over-long clips (>120s single clip is
   rejected by every backend). Warnings do not block; errors do.

2. **Route by the table, never by habit.** The tool applies this
   decision table (see `references/backends.md`):

   | Situation | Route |
   |---|---|
   | budget=free, NVIDIA ≥4GB VRAM | `sadtalker-local` (512px) |
   | budget=free, NVIDIA 2GB (e.g. GeForce 930MX class) | `sadtalker-local` 256px — very slow; price cloud GPU as the alternative |
   | budget=free, no/weak GPU | no free route exists — say so honestly, offer `sadtalker-cloud-gpu` (cents-per-clip class) |
   | quality=studio, budget allows | `heygen-api`, then `hedra-api` |
   | stylized/cartoon/non-human face | API route (`hedra-api`/`heygen-api`) — SadTalker needs photographic human faces |
   | quick draft, any GPU | cheapest feasible route, 256px |

   Read the tool's `reason` field into your report — the user should see
   *why* this backend, not just which.

3. **Wire the voice in the script's language.** German script →
   German TTS voice, Persian script → Persian voice. Never synthesize a
   German script with an English voice (umlauts/ß mispronounce, rhythm
   breaks). Options: Piper (local, free — `thorsten` for de, fa voices
   for Persian), Edge-TTS (free, needs network), ElevenLabs (paid).
   Synthesize to WAV first, then re-run preflight on the WAV
   (`--audio voice.wav`) for an exact duration check. Details in
   `references/tts.md`.

4. **Respect the known pitfalls.** Before rendering, read
   `references/pitfalls.md`: SadTalker needs human photographic faces
   (cartoon/fox/mask fails), pin a SadTalker commit (upstream quiet
   since 2024-06), audio over ~30s gets risky on low VRAM, commercial
   APIs bill per minute — always render a 5-second test clip first.

5. **Know the limits — and say them.** This skill routes and
   preflights; it does not render video and does not call any API.
   Cost tiers are indicative (documented Oct 2026) — always re-verify
   the live pricing page before spending, and say that you did. It
   does not generate the portrait or write the script. SadTalker
   install help is pointers, not a support contract.

## Backends at a glance

- **sadtalker-local** — free, offline, CUDA/NVIDIA. Good 512px on
  4GB+ VRAM; 256px-only and very slow on 2GB; human faces only.
- **sadtalker-cloud-gpu** — same free software on a rented RTX
  4090-class pod; cents-per-clip class; good when the local GPU is
  too weak.
- **hedra-api** — commercial, expressive, handles stylized faces
  better; per-minute billing; needs API key.
- **heygen-api** — commercial, studio-grade lip sync, 1500+ stock
  avatars, voice cloning; per-minute billing; needs API key.

Full matrix, install pointers and pricing-page links:
`references/backends.md`. TTS voice wiring per language:
`references/tts.md`.

## Reporting

Quote the tool's exit code and the chosen `backend_id` with its
`reason`. List every preflight error you fixed and every warning you
accepted. If budget=free produced no route, report that plainly —
do not silently upgrade the user to a paid backend.

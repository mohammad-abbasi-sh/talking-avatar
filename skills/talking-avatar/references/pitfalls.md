# Pitfalls — the failures that waste renders

Learned from operating talking-avatar jobs (and watching agents fail
them). Read before rendering.

## Faces

1. **SadTalker needs a human photographic face.** Cartoon, anime,
   fox/animal muzzle, mask, heavy stylization → broken output or a
   crash. Route non-human faces to Hedra/HeyGen APIs.
2. **Face must be front-facing and centered.** Profile shots and
   occluded faces (sunglasses, hand over mouth) degrade lip sync.
3. **512px portrait for 512px output.** Upscaling a 256px face does
   not add detail the model can use.
4. **One face per image.** Group photos confuse face detection —
   crop to one face first.

## GPUs and performance

5. **2GB VRAM (GeForce 930MX class) is the practical floor** for
   SadTalker — 256px only, very slow. Don't promise a same-day 512px
   render on it.
6. **Non-NVIDIA GPUs are experimental** for SadTalker (CUDA-focused
   upstream). Apple Silicon / AMD paths exist in forks, not in the
   mainline flow this skill assumes.
7. **VRAM grows with clip length.** A 60s clip on a 4GB card can OOM
   where 30s worked. Split long scripts.

## SadTalker operations

8. **Pin a commit.** Upstream is quiet since 2024-06 (★14k, 600+
   issues). A floating `git pull` on install day is how fresh
   environments break.
9. **Checkpoint downloads are large** (~GBs). First install needs
   disk space and patience, not just GPU.
10. **Audio format matters.** WAV at 16kHz-ish; exotic codecs and
    very long MP3s cause silent failures. The preflight only trusts
    WAV for exact duration.
11. **`--still` mode exists** for a reason: when head motion looks
    noisy, a static head with moving lips often looks better.

## APIs and money

12. **Always render a 5-second test clip first** on any paid API.
    Lip-sync quality varies by face; a test costs cents, a full
    re-render costs minutes.
13. **APIs bill per generated minute** — failed renders usually bill
    too. That's why preflight runs *before* the API call.
14. **Terminate rented GPU pods.** Idle pods, not renders, are the
    typical cloud-GPU bill shock.
15. **Re-verify pricing before every paid run.** Pricing pages change;
    this skill's tiers are indicative (Oct 2026).

## Audio and script

16. **>120s single clips are rejected by every backend.** Split
    first; stitch after.
17. **German umlauts/ß, Persian ZWNJ phrasing** — spot-check the
    synthesized WAV before rendering video. A mispronounced script
    means re-rendering, not re-synthesizing.
18. **Silence at the head/tail.** 0.3–0.5s of silence avoids clipped
    first/last phonemes.

## Agent discipline

19. **Never report "rendered" from a preflight.** Exit 0 from the
    router means "route decided", not "video exists".
20. **Quote the route reason.** The user chose a budget; show them the
    backend and why — especially when budget=free produced no route.

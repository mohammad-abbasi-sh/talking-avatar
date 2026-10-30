#!/usr/bin/env python3
"""avatar_route.py — deterministic talking-avatar backend router + preflight.

Zero-dependency (Python standard library only). It does NOT render video
and does NOT call any API. It does two honest, mechanical jobs:

  1. PREFLIGHT: validate the portrait image and the audio/script the agent
     is about to send to a talking-avatar backend, catching the failures
     that waste paid renders (corrupt files, tiny faces, wrong formats,
     over-long audio).
  2. ROUTE: pick the right backend (free local SadTalker / cloud GPU /
     Hedra API / HeyGen API) from the budget, quality target, GPU/VRAM
     and language — with the reasoning written down and priced as an
     *estimate* the user must re-verify before spending.

Exit codes: 0 = route decided · 1 = preflight errors, no route ·
2 = usage error (bad JSON, unknown budget/quality, missing fields).

Usage:
    python3 avatar_route.py --job job.json [--json]
    python3 avatar_route.py --image face.png --audio voice.wav \\
        --budget free --quality good --vram-gb 2 --lang de [--json]
    python3 avatar_route.py --list-backends [--json]
"""

import argparse
import json
import struct
import sys
import wave
from pathlib import Path

VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Backend registry.
#
# Cost/quality/time figures below are INDICATIVE (documented Oct 2026).
# They are cost TIER labels, not live prices. The tool never claims a
# live price; every output tells the user to re-verify pricing pages
# before spending. SadTalker capability notes reflect the upstream
# README as of 2024-06 (the repo went quiet; pin a known-good commit).
# ---------------------------------------------------------------------------

COST_TIERS = ["free", "cents-per-clip", "paid-per-minute"]

BACKENDS = [
    {
        "id": "sadtalker-local",
        "name": "SadTalker (local, self-hosted)",
        "cost_tier": "free",
        "quality": "good",          # 512px output on a decent GPU
        "type": "local",
        "url": "https://github.com/OpenTalker/SadTalker",
        "notes": (
            "Free and offline. CUDA/NVIDIA focused; needs ~4GB+ VRAM for "
            "512px, 2GB GPUs only manage 256px and render very slowly "
            "(order of 10x realtime). Works on HUMAN photographic faces — "
            "cartoons, animal muzzles, masks and heavy stylization fail or "
            "look broken. Upstream quiet since 2024-06: pin a known commit, "
            "expect dependency friction on fresh machines."
        ),
    },
    {
        "id": "sadtalker-cloud-gpu",
        "name": "SadTalker on rented GPU (RunPod / Vast.ai class)",
        "cost_tier": "cents-per-clip",
        "quality": "good",
        "type": "cloud-gpu",
        "url": "https://www.runpod.io",
        "notes": (
            "Same free software, rented RTX 4090-class GPU. Indicative "
            "class: $0.3-0.7/hr (Oct 2026 — re-verify); a 30s clip is "
            "cents. Good middle ground when the local GPU is too weak. "
            "Needs a cloud account and ~15 min of setup per session."
        ),
    },
    {
        "id": "hedra-api",
        "name": "Hedra API",
        "cost_tier": "paid-per-minute",
        "quality": "good",
        "type": "api",
        "url": "https://www.hedra.com",
        "notes": (
            "Commercial API, expressive output, handles stylized faces "
            "better than SadTalker. Billed per generated minute (re-verify "
            "current pricing). Needs an API key."
        ),
    },
    {
        "id": "heygen-api",
        "name": "HeyGen API",
        "cost_tier": "paid-per-minute",
        "quality": "studio",
        "type": "api",
        "url": "https://www.heygen.com",
        "notes": (
            "Commercial API, studio-grade lip sync, 1500+ stock avatars, "
            "voice cloning. Billed per credit/minute (re-verify current "
            "pricing). Needs an API key. Best quality of the four when "
            "budget allows."
        ),
    },
]

WPM = {"en": 150, "de": 140, "fa": 130, "ar": 130, "es": 150,
       "fr": 150, "tr": 140, "ur": 130}
DEFAULT_WPM = 140


# ---------------------------------------------------------------------------
# Preflight: image
# ---------------------------------------------------------------------------

def read_png_dimensions(path):
    """Return (width, height) for a PNG, or raise ValueError."""
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG file")
        length = struct.unpack(">I", f.read(4))[0]
        ctype = f.read(4)
        if ctype != b"IHDR" or length != 13:
            raise ValueError("first chunk is not IHDR")
        data = f.read(13)
        if len(data) != 13:
            raise ValueError("truncated IHDR")
        w, h = struct.unpack(">II", data[:8])
        return w, h


def read_jpeg_dimensions(path):
    """Return (width, height) for a JPEG by scanning for SOF markers."""
    data = Path(path).read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG file (missing SOI)")
    pos = 2
    # Markers without a length field:
    standalone = {0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8 + 1))
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError(f"expected marker at offset {pos}")
        marker = data[pos + 1]
        pos += 2
        if marker in standalone:
            continue
        if pos + 2 > len(data):
            raise ValueError("truncated segment length")
        seg_len = struct.unpack(">H", data[pos:pos + 2])[0]
        if seg_len < 2:
            raise ValueError("invalid segment length")
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0/1/2
            if pos + 7 > len(data):
                raise ValueError("truncated SOF segment")
            h, w = struct.unpack(">HH", data[pos + 3:pos + 7])
            return w, h
        pos += seg_len
    raise ValueError("no SOF marker found (not a baseline JPEG)")


def check_image(path_str):
    """Validate a portrait image. Returns dict with errors/warnings/info."""
    out = {"errors": [], "warnings": [], "info": {}}
    if not path_str:
        out["errors"].append("IMAGE-01: no image path given")
        return out
    p = Path(path_str)
    if not p.is_file():
        out["errors"].append(f"IMAGE-01: image not found: {path_str}")
        return out
    suffix = p.suffix.lower()
    dims = None
    try:
        if suffix == ".png":
            dims = read_png_dimensions(p)
        elif suffix in (".jpg", ".jpeg"):
            dims = read_jpeg_dimensions(p)
        else:
            out["errors"].append(
                f"IMAGE-02: unsupported image format '{suffix or '(none)'}' — "
                "use PNG or JPEG for talking-avatar backends")
            return out
    except ValueError as e:
        out["errors"].append(f"IMAGE-02: unreadable/corrupt image: {e}")
        return out
    except OSError as e:
        out["errors"].append(f"IMAGE-02: cannot read image: {e}")
        return out
    w, h = dims
    out["info"] = {"format": suffix.lstrip("."), "width": w, "height": h}
    small = min(w, h)
    if small < 128:
        out["errors"].append(
            f"IMAGE-03: portrait is {w}x{h} — below 128px, no backend can "
            "build a face from this")
    elif small < 256:
        out["warnings"].append(
            f"IMAGE-03: portrait is {w}x{h} — under 256px; expect soft "
            "output, prefer 512px+ for SadTalker")
    ratio = max(w, h) / max(small, 1)
    if ratio > 3:
        out["warnings"].append(
            f"IMAGE-04: extreme aspect ratio {w}x{h} — crop to a "
            "face-centered square-ish portrait first")
    size_kb = p.stat().st_size / 1024
    if size_kb > 10 * 1024:
        out["warnings"].append(
            f"IMAGE-05: file is {size_kb/1024:.1f}MB — some APIs reject "
            ">10MB uploads; downscale first")
    return out


# ---------------------------------------------------------------------------
# Preflight: audio / script
# ---------------------------------------------------------------------------

def check_audio(audio_path, text, language):
    """Validate audio file or estimate script duration. Returns dict."""
    out = {"errors": [], "warnings": [], "info": {}}
    if audio_path:
        p = Path(audio_path)
        if not p.is_file():
            out["errors"].append(f"AUDIO-01: audio file not found: {audio_path}")
            return out
        suffix = p.suffix.lower()
        if suffix == ".wav":
            try:
                with wave.open(str(p), "rb") as w:
                    nframes, framerate = w.getnframes(), w.getframerate()
                    duration = nframes / framerate if framerate else 0
            except (wave.Error, EOFError, OSError) as e:
                out["errors"].append(f"AUDIO-02: unreadable WAV: {e}")
                return out
            out["info"] = {"format": "wav", "duration_s": round(duration, 1),
                           "sample_rate": framerate}
        elif suffix in (".mp3", ".m4a", ".ogg", ".flac"):
            out["warnings"].append(
                f"AUDIO-03: '{suffix}' duration cannot be read without "
                "decoders — pass --duration-hint-s or convert to WAV for "
                "an exact preflight")
            out["info"] = {"format": suffix.lstrip("."), "duration_s": None}
        else:
            out["errors"].append(
                f"AUDIO-02: unsupported audio format '{suffix}' — use WAV "
                "for exact preflight, MP3/M4A/OGG otherwise")
            return out
    elif text:
        words = len(text.split())
        wpm = WPM.get((language or "").lower(), DEFAULT_WPM)
        duration = words / wpm * 60
        out["info"] = {"format": "text-script", "words": words,
                       "duration_s": round(duration, 1),
                       "duration_estimated": True,
                       "wpm_used": wpm}
    else:
        out["errors"].append("AUDIO-04: neither audio file nor script text given")
        return out

    dur = out["info"].get("duration_s")
    if dur is not None:
        if dur <= 0:
            out["errors"].append("AUDIO-05: zero-length audio")
        elif dur > 120:
            out["errors"].append(
                f"AUDIO-05: {dur:.0f}s exceeds the ~120s single-clip limit "
                "of every backend — split the script first")
        elif dur > 30:
            out["warnings"].append(
                f"AUDIO-05: {dur:.0f}s is long — SadTalker VRAM use grows "
                "with length; APIs bill per minute. Consider splitting.")
    return out


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def sadtalker_feasible(job):
    """Decide whether SadTalker-local can run. Returns (ok, reason)."""
    vendor = (job.get("gpu_vendor") or "none").lower()
    vram = job.get("vram_gb") or 0
    if vendor != "nvidia":
        return False, (f"GPU vendor is '{vendor}' — SadTalker upstream is "
                       "CUDA/NVIDIA focused; non-NVIDIA setups are "
                       "experimental at best")
    if vram >= 4:
        return True, f"{vram}GB VRAM — 512px SadTalker renders fine"
    if vram >= 2:
        return True, (f"{vram}GB VRAM — 256px only, renders very slowly "
                      "(order of 10x realtime); cloud GPU is worth pricing")
    return False, (f"{vram}GB VRAM — below the ~2GB practical floor for "
                   "SadTalker; use cloud GPU or an API")


def route(job):
    """Apply the decision table. Returns (result_dict, exit_code)."""
    image = check_image(job.get("image"))
    audio = check_audio(job.get("audio"), job.get("text"),
                        job.get("language", "en"))
    errors = image["errors"] + audio["errors"]
    warnings = image["warnings"] + audio["warnings"]

    budget = (job.get("budget") or "any").lower()
    quality = (job.get("quality") or "good").lower()
    if budget not in ("free", "low", "mid", "any"):
        return ({"errors": [f"unknown budget '{budget}' — free|low|mid|any"]}, 2)
    if quality not in ("draft", "good", "studio"):
        return ({"errors": [f"unknown quality '{quality}' — draft|good|studio"]}, 2)

    feasible, st_reason = sadtalker_feasible(job)

    candidates = []
    for b in BACKENDS:
        bid = b["id"]
        ok, reason = True, ""
        if bid == "sadtalker-local":
            ok, reason = feasible, st_reason
            if ok and job.get("vram_gb", 0) < 4:
                warnings.append(
                    "SadTalker-local at 256px: quality is 'draft'-class, "
                    "not 'good'. Pick cloud GPU or an API for good+.")
        if bid == "sadtalker-cloud-gpu" and budget == "free":
            ok, reason = False, "rented GPU is not free"
        if b["cost_tier"] == "paid-per-minute" and budget in ("free", "low"):
            ok, reason = False, f"budget '{budget}' excludes paid APIs"
        if ok:
            # Rank: for studio requests quality dominates cost;
            # otherwise cheapest tier wins, then quality.
            if quality == "studio":
                rank = (0 if b["quality"] == "studio" else 1,
                        COST_TIERS.index(b["cost_tier"]))
            else:
                rank = (COST_TIERS.index(b["cost_tier"]),
                        -["draft", "good", "studio"].index(b["quality"]))
            candidates.append((rank, b, reason or "fits constraints"))

    if errors:
        return ({"preflight": {"errors": errors, "warnings": warnings},
                 "route": None,
                 "note": "Fix preflight errors before routing — a corrupt "
                         "asset wastes a paid render."}, 1)

    if not candidates:
        alt = ("Cheapest paid option is sadtalker-cloud-gpu "
               "(cents-per-clip class, re-verify pricing) or the Hedra/HeyGen "
               "APIs.")
        return ({"preflight": {"errors": errors, "warnings": warnings},
                 "route": None,
                 "note": "No backend fits budget/quality/GPU together. " + alt}, 1)

    candidates.sort(key=lambda c: c[0])
    chosen_rank, chosen, chosen_reason = candidates[0]
    alternatives = [{"id": b["id"], "name": b["name"],
                     "cost_tier": b["cost_tier"], "reason": r}
                    for _, b, r in candidates[1:]]

    # TTS hint: text route needs a voice in the script language.
    tts_hint = None
    if job.get("text"):
        lang = (job.get("language") or "en").lower()
        tts_hint = tts_recommendation(lang)

    dur = audio["info"].get("duration_s")
    result = {
        "route": {
            "backend_id": chosen["id"],
            "backend_name": chosen["name"],
            "backend_url": chosen["url"],
            "reason": chosen_reason,
            "cost_tier": chosen["cost_tier"],
            "cost_note": ("Indicative tier only — re-verify the live pricing "
                          "page before spending."),
            "backend_notes": chosen["notes"],
        },
        "alternatives": alternatives,
        "preflight": {
            "errors": errors,
            "warnings": warnings,
            "image": image["info"],
            "audio": audio["info"],
        },
        "tts_hint": tts_hint,
        "next_steps": next_steps(chosen["id"], job, dur),
    }
    return result, 0


def tts_recommendation(lang):
    table = {
        "de": ("Piper (local, free, e.g. thorsten voice) or Edge-TTS de-DE "
               "(free, needs network) — never synthesize a German script "
               "with an English voice; umlauts and ß mispronounce."),
        "fa": ("Piper fa voices (local, free) or Edge-TTS fa-IR — check "
               "the voice handles Persian digits and ZWNJ phrasing."),
        "en": ("Piper (local, free) or Edge-TTS en-US/en-GB — match the "
               "audience accent."),
    }
    return table.get(lang, "Use a TTS voice in the script language "
                           "(Piper local / Edge-TTS) — never cross voices "
                           "across languages.")


def next_steps(backend_id, job, duration_s):
    steps = ["Run the preflight again on the FINAL assets (exit 0 = go)."]
    if backend_id == "sadtalker-local":
        steps += [
            "Clone SadTalker at a pinned commit (upstream quiet since "
            "2024-06) and install per its README (conda env, checkpoints "
            "download).",
            "Portrait must be a human photographic face, 512px, "
            "face-centered. Cartoons/muzzles fail.",
            "Render: python inference.py --driven_audio <wav> "
            "--source_image <png> --result_dir out/ "
            "(add --still for a static head when motion looks noisy).",
        ]
    elif backend_id == "sadtalker-cloud-gpu":
        steps += [
            "Rent an RTX 4090-class pod (RunPod/Vast.ai), pull a SadTalker "
            "template or install manually, upload portrait + WAV, render, "
            "download — terminate the pod when done.",
        ]
    elif backend_id in ("hedra-api", "heygen-api"):
        steps += [
            "Create the API key, check the CURRENT pricing page, render a "
            "5-second test clip first — then the full script.",
            ("For HeyGen: consider a stock avatar instead of uploading a "
             "portrait when the face is not photographic.")
            if backend_id == "heygen-api" else
            "For Hedra: upload portrait + audio, pick the expressive model.",
        ]
    if job.get("text") and not job.get("audio"):
        steps.insert(1, "Synthesize the script to WAV first "
                        "(see tts_hint), then re-run preflight on the WAV.")
    if duration_s and duration_s > 30:
        steps.append("Long clip: split into <=30s segments and stitch — "
                     "safer on VRAM and cheaper on APIs.")
    return steps


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        description="Route a talking-avatar job to the right backend "
                    "and preflight its assets. Stdlib only.")
    p.add_argument("--job", help="JSON file with the job request")
    p.add_argument("--image", help="portrait image path (PNG/JPEG)")
    p.add_argument("--audio", help="driving audio path (WAV for exact check)")
    p.add_argument("--text", help="script text (TTS route)")
    p.add_argument("--duration-hint-s", type=float, default=None)
    p.add_argument("--language", default="en")
    p.add_argument("--budget", default="any",
                   help="free|low|mid|any")
    p.add_argument("--quality", default="good",
                   help="draft|good|studio")
    p.add_argument("--vram-gb", type=float, default=0)
    p.add_argument("--gpu-vendor", default="none",
                   help="nvidia|amd|apple|none")
    p.add_argument("--json", action="store_true",
                   help="machine-readable output")
    p.add_argument("--list-backends", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_backends:
        payload = {"backends": BACKENDS,
                   "cost_tiers": COST_TIERS,
                   "note": "Cost tiers are indicative (Oct 2026) — "
                           "re-verify live pricing before spending."}
        print(json.dumps(payload, indent=2, ensure_ascii=False)
              if args.json else
              "\n".join(f"{b['id']:22} {b['cost_tier']:15} {b['name']}"
                        for b in BACKENDS))
        return 0

    if args.job:
        try:
            job = json.loads(Path(args.job).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: cannot read job JSON: {e}", file=sys.stderr)
            return 2
    else:
        job = {
            "image": args.image,
            "audio": args.audio,
            "text": args.text,
            "duration_hint_s": args.duration_hint_s,
            "language": args.language,
            "budget": args.budget,
            "quality": args.quality,
            "vram_gb": args.vram_gb,
            "gpu_vendor": args.gpu_vendor,
        }

    result, code = route(job)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human(result, code)
    return code


def print_human(result, code):
    pre = result.get("preflight", {})
    for e in pre.get("errors", []):
        print(f"ERROR  {e}")
    for w in pre.get("warnings", []):
        print(f"WARN   {w}")
    r = result.get("route")
    if r:
        print(f"\nROUTE  {r['backend_id']} — {r['backend_name']}")
        print(f"       reason: {r['reason']}")
        print(f"       cost:   {r['cost_tier']} ({r['cost_note']})")
        print(f"       docs:   {r['backend_url']}")
        for a in result.get("alternatives", []):
            print(f"ALT    {a['id']} ({a['cost_tier']}): {a['reason']}")
    if result.get("tts_hint"):
        print(f"\nTTS    {result['tts_hint']}")
    for s in result.get("next_steps", []):
        print(f"NEXT   {s}")
    if result.get("note"):
        print(f"NOTE   {result['note']}")


if __name__ == "__main__":
    sys.exit(main())

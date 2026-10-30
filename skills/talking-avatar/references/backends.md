# Backend matrix — the four routes, honestly compared

Surveyed 2026-10-30. Pricing figures are **indicative tiers, not live
prices** — re-verify the linked pricing page before spending. This is a
routing decision aid, not a quote.

## The four routes

### 1. sadtalker-local — SadTalker, self-hosted

- Repo: https://github.com/OpenTalker/SadTalker (★14k, quiet since 2024-06)
- Cost: **free** (electricity + your time)
- Quality: good at 512px; draft-class at 256px
- GPU: NVIDIA/CUDA. ≥4GB VRAM → 512px fine. 2GB (e.g. GeForce 930MX
  class) → 256px only, very slow (order of 10x realtime). <2GB →
  infeasible.
- Faces: **human photographic faces only.** Cartoons, animal muzzles,
  masks, heavy stylization fail or look broken — route those to an API.
- Setup: conda env + checkpoint downloads, ~30–60 min first time.
  **Pin a known-good commit** — upstream is stale; fresh installs hit
  dependency friction.
- Audio: WAV 16kHz-ish works best; keep clips ≤30s on weak GPUs.

### 2. sadtalker-cloud-gpu — SadTalker on a rented GPU

- Providers: RunPod, Vast.ai (template or manual install)
- Cost: **cents-per-clip class** (indicative class $0.3–0.7/hr for
  RTX 4090, Oct 2026 — re-verify). A 30s clip is cents.
- Quality: same as local SadTalker, but fast.
- When: local GPU too weak, budget "low", one-off renders.
- Discipline: upload portrait + WAV, render, download, **terminate the
  pod** — idle pods are where the money goes.

### 3. hedra-api — Hedra

- Site: https://www.hedra.com
- Cost: **paid-per-minute** (re-verify current pricing)
- Quality: good; expressive output; handles stylized faces better than
  SadTalker.
- Needs: API key. Render a 5s test clip before the full script.

### 4. heygen-api — HeyGen

- Site: https://www.heygen.com · official skill: heygen-com/skills (★518)
- Cost: **paid-per-minute** (re-verify current pricing)
- Quality: **studio** — best lip sync of the four; 1500+ stock avatars;
  voice cloning.
- Needs: API key. Consider a stock avatar instead of uploading a
  portrait when the face is not photographic.

## What the neighbors do (and don't)

Single-vendor agent skills exist and are fine at their job — they are
not routers:

- **creatify-ai/ai-avatar-video** (★36) — Creatify API only; script and
  persona guides, 1500+ Creatify avatars. No local/free route, no
  backend choice.
- **beatra-ai/talking-avatar-video-skill** (★5) — Beatra API only;
  needs a Beatra account + credits.
- **heygen-com/skills** (★518) — HeyGen only.
- **Hedra plugins** (e.g. mattstvartak/openclaw-hedra-plugin,
  susan4731-wilfordf/ai-skills) — Hedra only.
- **digitalsamba/claude-code-video-toolkit** (★2,335) — broad video
  toolkit with cloud-GPU paths; SadTalker only via cloud integration,
  not a standalone local skill.
- **No SadTalker MCP server exists** (searched 2026-10-30).

This skill sits above them: preflight + route, then hand off to
whichever backend fits.

## Decision rules (encoded in `scripts/avatar_route.py`)

1. Preflight errors → no route. Fix the asset.
2. budget=free → only `sadtalker-local` qualifies. If the GPU can't
   run it, report "no free route" honestly — don't silently upgrade
   to paid.
3. budget=low → free first, then cloud-GPU.
4. quality=studio → `heygen-api`, then `hedra-api`.
5. Non-human/stylized face → API routes only.
6. Everything else → cheapest feasible tier wins.

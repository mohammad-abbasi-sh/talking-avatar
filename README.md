# talking-avatar — the router skill for talking-head video

Agents pick a talking-avatar backend by habit: whichever vendor's skill
is installed, every portrait becomes that vendor's render. The habit
wastes money and time. A free local SadTalker run is right for a draft
on a good GPU; a HeyGen render is right for studio quality with budget;
a cartoon fox face fails on SadTalker no matter how good the GPU is; a
2GB laptop GPU turns a local SadTalker job into a bad afternoon.

**talking-avatar** is the decision layer the single-vendor skills don't
have: a standard Agent Skill + a zero-dependency router/preflight tool
+ a Cursor rule + an MCP server. **Preflight the assets, route to the
backend that fits, then render.**

## The gap

Surveyed 2026-10-30 (GitHub API + web). What exists:

| Project | What it is | What it isn't |
|---|---|---|
| `heygen-com/skills` (★518) | Official HeyGen skill | HeyGen only |
| `creatify-ai/ai-avatar-video` (★36) | Creatify API skill | Creatify only |
| `beatra-ai/talking-avatar-video-skill` (★5) | Beatra API skill, credits | Beatra only |
| Hedra plugins (OpenClaw etc.) | Hedra API | Hedra only |
| `digitalsamba/claude-code-video-toolkit` (★2,335) | Broad video toolkit | SadTalker only via cloud; not a standalone local skill |
| Higgsfield MCP | Commercial all-in-one | Not a skill, not local, not free |

No standalone **local SadTalker** agent skill exists. No **SadTalker MCP**
exists. And nothing **routes across backends** — every skill assumes
its own vendor. That's the gap this fills.

## Before / after

**Before** — an agent with a HeyGen skill and a portrait + German script:

> Renders on HeyGen. Costs credits. Nobody asked whether a free local
> run would do, or whether the laptop's 2GB GPU makes local SadTalker
> pointless.

**After** — same task with this skill:

```bash
$ python3 skills/talking-avatar/scripts/avatar_route.py \
    --image face.png --text "Guten Tag!" --lang de \
    --budget any --quality good --vram-gb 2 --gpu-vendor nvidia

WARN   SadTalker-local at 256px: quality is 'draft'-class, not 'good'...

ROUTE  sadtalker-local — SadTalker (local, self-hosted)
       reason: 2.0GB VRAM — 256px only, renders very slowly (order of 10x realtime); cloud GPU is worth pricing
       cost:   free (Indicative tier only — re-verify the live pricing page before spending.)
ALT    sadtalker-cloud-gpu (cents-per-clip): fits constraints
ALT    heygen-api (paid-per-minute): fits constraints
TTS    Piper (local, free, e.g. thorsten voice) or Edge-TTS de-DE ...
NEXT   Synthesize the script to WAV first (see tts_hint), then re-run preflight on the WAV.
NEXT   Clone SadTalker at a pinned commit ...
```

The agent now knows: free route exists but is slow at 256px, the
cloud-GPU alternative costs cents, and the German script needs a German
voice. That's the whole point.

## What's inside

```
skills/talking-avatar/
  SKILL.md                  # the skill: contract, decision table, limits
  scripts/avatar_route.py   # zero-dependency router + preflight (stdlib only)
  references/backends.md    # 4-backend matrix, install pointers, pricing links
  references/tts.md         # per-language voice wiring (de/fa/en)
  references/pitfalls.md    # 20 known failures
mcp-server/                 # stdio MCP: route_avatar_job, preflight_avatar, list_avatar_backends
cursor/                     # talking-avatar.mdc rule + Windsurf/Cline/Continue install notes
dist/                       # talking-avatar-skill.zip — upload to Claude.ai
tests/                      # 60 tests, all passing (2026-10-30)
```

The four routed backends: **sadtalker-local** (free, NVIDIA/CUDA,
human faces only) · **sadtalker-cloud-gpu** (same software, rented
RTX 4090-class, cents-per-clip class) · **hedra-api** (expressive,
stylized faces OK) · **heygen-api** (studio quality). Cost tiers are
indicative (Oct 2026) — the tool says so in every output.

## Install

**Claude Code** — copy the skill folder:

```bash
cp -r skills/talking-avatar ~/.claude/skills/
```

**Claude.ai** — upload `dist/talking-avatar-skill.zip` as a skill
(Settings → Skills). Rebuild it with:

```bash
python3 - <<'EOF'
import zipfile
from pathlib import Path
root = Path("skills/talking-avatar")
with zipfile.ZipFile("dist/talking-avatar-skill.zip", "w",
                     zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to("skills"))
print("zip rebuilt")
EOF
```

**Cursor** — see `cursor/README.md` (`talking-avatar.mdc` + notes for
Windsurf, Cline, Continue).

**Any MCP client:**

```json
{ "mcpServers": { "talking-avatar":
  { "command": "python3",
    "args": ["/path/to/mcp-server/avatar_router_mcp_server.py"] } } }
```

## The contract (short)

1. Preflight first, with the tool — never send a bad asset to a render.
2. Route by the table, never by vendor habit. Read the `reason` into
   your report.
3. Voice in the script's language (German script → German voice).
4. Commercial APIs: 5-second test clip first; re-verify pricing.
5. Never report "rendered" from a preflight — exit 0 means "route
   decided".

## Roadmap

- v0.2: `--fix`-style portrait helpers (auto-crop to face-centered
  square via stdlib? no — needs a face detector; instead: validate
  crop suggestions), Piper/Edge-TTS command builders per language.
- v0.3: RunPod/Vast.ai one-shot job templates for the cloud-GPU route.
- v0.4: Render-result QA checklist (lip-sync sanity signals an agent
  can check without watching video).

## Limits (stated plainly)

- Routes and preflights; does not render, does not call APIs.
- Cost figures are tiers, not quotes — re-verify before spending.
- SadTalker install pointers, not a support contract (upstream quiet
  since 2024-06; pin a commit).
- No portrait generation, no script writing.

## License

MIT — Mohammad Abbasi, 2026.

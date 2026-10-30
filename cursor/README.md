# Install in other agents

The skill is a plain folder: `skills/talking-avatar/` with `SKILL.md`,
`scripts/avatar_route.py` (stdlib-only) and `references/`. The
`cursor/talking-avatar.mdc` rule carries the same contract.

## Cursor

Copy the rule file into your project's rules:

```bash
cp cursor/talking-avatar.mdc .cursor/rules/talking-avatar.mdc
cp -r skills/talking-avatar .cursor/rules/talking-avatar-files/
```

Or add it globally in Cursor Settings → Rules. The rule auto-attaches
when you work with portrait/audio files (`*.png`, `*.jpg`, `*.wav`,
`*.mp3`).

## Windsurf

Copy the skill folder into Windsurf's rules directory and reference it
from `.windsurf/rules/`:

```bash
mkdir -p .windsurf/rules
cp -r skills/talking-avatar .windsurf/rules/
```

Add a short pointer in your workspace rules file so the agent loads
`SKILL.md` when a talking-avatar task appears.

## Cline / Roo Code

Copy the skill into Cline's custom instructions or reference it from
`.clinerules`:

```bash
cp -r skills/talking-avatar .clinerules/talking-avatar
```

Then add one line to `.clinerules`:

```text
When a task involves talking-avatar video (portrait + script/audio),
read .clinerules/talking-avatar/SKILL.md first and route with
.clinerules/talking-avatar/scripts/avatar_route.py before rendering.
```

## Continue

Add to `~/.continue/config.yaml`:

```yaml
rules:
  - "When a task involves talking-avatar video, read "
    "<path-to>/skills/talking-avatar/SKILL.md and route with "
    "scripts/avatar_route.py (Python stdlib only) before rendering."
```

## MCP clients (Claude Code, Cursor, any MCP host)

`mcp-server/avatar_router_mcp_server.py` is stdlib-only stdio MCP:

```json
{
  "mcpServers": {
    "talking-avatar": {
      "command": "python3",
      "args": ["/path/to/mcp-server/avatar_router_mcp_server.py"]
    }
  }
}
```

Tools: `route_avatar_job`, `preflight_avatar`, `list_avatar_backends`.
